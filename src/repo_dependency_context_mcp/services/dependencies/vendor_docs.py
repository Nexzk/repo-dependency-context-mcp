from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from repo_dependency_context_mcp.db.models import Chunk, DependencyDoc, Document, Source
from repo_dependency_context_mcp.services.ingest.sync_state import SyncStateService
from repo_dependency_context_mcp.services.retrieval.embedding import embed_text


@dataclass(slots=True)
class VendorDocCandidate:
    doc_type: str
    authority: str
    url: str
    title: str
    section_title: str | None
    raw_text: str
    version_range: str | None
    metadata_json: dict[str, object] | None = None


@dataclass(slots=True)
class VendorDocFetchRequest:
    doc_type: str
    url: str
    version_range: str | None = None


@dataclass(slots=True)
class VendorDocDiscoveryRequest:
    index_url: str
    doc_type: str
    version_range: str | None = None
    include_url_prefixes: list[str] | None = None
    include_doc_types: list[str] | None = None
    max_pages: int = 10


class VendorDocIngestService:
    def __init__(self, session: Session, official_domains: dict[str, list[str]]) -> None:
        self.session = session
        self.official_domains = official_domains

    def fetch_and_ingest(
        self,
        package_name: str,
        ecosystem: str,
        requests: list[VendorDocFetchRequest],
    ) -> int:
        sync_state = SyncStateService(self.session)
        run = sync_state.start_run(
            tenant_id=_global_tenant_id(),
            repo_id=None,
            source_kind="vendor_docs",
            scope_key=_scope_key(package_name, ecosystem),
            cursor_kind="vendor_doc_snapshot",
        )
        candidates: list[VendorDocCandidate] = []
        try:
            with httpx.Client(follow_redirects=True, timeout=10.0) as client:
                for request in requests:
                    allowed_domains = self.official_domains.get(package_name, [])
                    if not self._is_allowed_domain(request.url, allowed_domains):
                        continue

                    response = client.get(
                        request.url,
                        headers=self._conditional_headers(request.url),
                    )
                    if response.status_code == 304:
                        continue
                    response.raise_for_status()
                    parser = _SimpleHtmlDocParser()
                    parser.feed(response.text)

                    candidates.append(
                        VendorDocCandidate(
                            doc_type=request.doc_type,
                            authority="official",
                            url=request.url,
                            title=parser.title or request.url,
                            section_title=_resolve_section_title(parser),
                            raw_text=parser.text_content(),
                            version_range=request.version_range,
                            metadata_json=_doc_structure_metadata(
                                parser,
                                response_headers=response.headers,
                            ),
                        )
                    )

            written = self.ingest_candidates(
                package_name=package_name,
                ecosystem=ecosystem,
                candidates=candidates,
                ingest_source="vendor_docs_fetcher",
            )
            sync_state.mark_success(
                run=run,
                cursor_after=_serialize_candidate_snapshot(
                    requests=requests,
                    candidates=candidates,
                    mode="fetch",
                ),
                items_seen=len(candidates),
                items_written=written,
            )
            return written
        except Exception as exc:
            sync_state.mark_failure(run=run, error=str(exc))
            raise

    def discover_and_ingest(
        self,
        package_name: str,
        ecosystem: str,
        requests: list[VendorDocDiscoveryRequest],
    ) -> int:
        sync_state = SyncStateService(self.session)
        run = sync_state.start_run(
            tenant_id=_global_tenant_id(),
            repo_id=None,
            source_kind="vendor_docs",
            scope_key=_scope_key(package_name, ecosystem),
            cursor_kind="vendor_doc_snapshot",
        )
        candidates: list[VendorDocCandidate] = []
        page_cache: dict[str, dict[str, object] | None] = {}
        try:
            with httpx.Client(follow_redirects=True, timeout=10.0) as client:
                for request in requests:
                    allowed_domains = self.official_domains.get(package_name, [])
                    if not self._is_allowed_domain(request.index_url, allowed_domains):
                        continue

                    response = client.get(request.index_url)
                    response.raise_for_status()
                    parser = _SimpleHtmlDocParser()
                    parser.feed(response.text)

                    page_urls = self._discover_page_urls(
                        index_url=request.index_url,
                        links=parser.links,
                        allowed_domains=allowed_domains,
                        include_url_prefixes=request.include_url_prefixes or [],
                        max_pages=request.max_pages,
                    )
                    for page_url in page_urls:
                        if page_url not in page_cache:
                            try:
                                page_response = client.get(
                                    page_url,
                                    headers=self._conditional_headers(page_url),
                                )
                                if page_response.status_code == 304:
                                    page_cache[page_url] = None
                                    continue
                                page_response.raise_for_status()
                            except Exception:
                                page_cache[page_url] = None
                                continue
                            page_parser = _SimpleHtmlDocParser()
                            page_parser.feed(page_response.text)
                            page_cache[page_url] = {
                                "title": page_parser.title or page_url,
                                "section_title": _resolve_section_title(page_parser),
                                "raw_text": page_parser.text_content(),
                                "metadata_json": _doc_structure_metadata(
                                    page_parser,
                                    response_headers=page_response.headers,
                                ),
                            }
                        page_data = page_cache[page_url]
                        if page_data is None:
                            continue
                        page_title = str(page_data["title"])
                        section_title = page_data.get("section_title")
                        raw_text = str(page_data["raw_text"])
                        resolved_doc_type = _infer_doc_type(
                            url=page_url,
                            title=page_title,
                            default_doc_type=request.doc_type,
                            include_doc_types=request.include_doc_types or [],
                        )
                        if resolved_doc_type is None:
                            continue
                        if (
                            request.include_doc_types
                            and resolved_doc_type not in request.include_doc_types
                        ):
                            continue
                        candidates.append(
                            VendorDocCandidate(
                                doc_type=resolved_doc_type,
                                authority="official",
                                url=page_url,
                                title=page_title,
                                section_title=(
                                    str(section_title) if section_title is not None else None
                                ),
                                raw_text=raw_text,
                                version_range=request.version_range,
                                metadata_json=dict(page_data.get("metadata_json", {})),
                            )
                        )

            written = self.ingest_candidates(
                package_name=package_name,
                ecosystem=ecosystem,
                candidates=candidates,
                ingest_source="vendor_docs_discovery",
            )
            sync_state.mark_success(
                run=run,
                cursor_after=_serialize_candidate_snapshot(
                    requests=requests,
                    candidates=candidates,
                    mode="discovery",
                ),
                items_seen=len(candidates),
                items_written=written,
            )
            return written
        except Exception as exc:
            sync_state.mark_failure(run=run, error=str(exc))
            raise

    def ingest_candidates(
        self,
        package_name: str,
        ecosystem: str,
        candidates: list[VendorDocCandidate],
        ingest_source: str = "vendor_docs",
    ) -> int:
        allowed_domains = self.official_domains.get(package_name, [])
        accepted = 0
        seen_urls: set[str] = set()

        for candidate in candidates:
            if candidate.url in seen_urls:
                continue
            seen_urls.add(candidate.url)
            if not self._is_allowed_domain(candidate.url, allowed_domains):
                continue

            existing = self.session.execute(
                select(DependencyDoc).where(DependencyDoc.url == candidate.url)
            ).scalar_one_or_none()
            candidate_metadata = getattr(candidate, "metadata_json", None) or {}
            metadata = {
                "ingest_source": ingest_source,
                **candidate_metadata,
            }
            if existing is not None:
                unchanged = (
                    existing.package_name == package_name
                    and existing.ecosystem == ecosystem
                    and existing.doc_type == candidate.doc_type
                    and existing.authority == "official"
                    and existing.version_range == candidate.version_range
                    and existing.title == candidate.title
                    and existing.section_title == candidate.section_title
                    and existing.raw_text == candidate.raw_text
                    and existing.metadata_json == metadata
                )
                if unchanged:
                    self._sync_section_index(
                        package_name=package_name,
                        ecosystem=ecosystem,
                        candidate=candidate,
                        metadata=metadata,
                    )
                    continue
                existing.package_name = package_name
                existing.ecosystem = ecosystem
                existing.doc_type = candidate.doc_type
                existing.authority = "official"
                existing.version_range = candidate.version_range
                existing.title = candidate.title
                existing.section_title = candidate.section_title
                existing.raw_text = candidate.raw_text
                existing.metadata_json = metadata
            else:
                self.session.add(
                    DependencyDoc(
                        package_name=package_name,
                        ecosystem=ecosystem,
                        doc_type=candidate.doc_type,
                        authority="official",
                        url=candidate.url,
                        version_range=candidate.version_range,
                        title=candidate.title,
                        section_title=candidate.section_title,
                        raw_text=candidate.raw_text,
                        metadata_json=metadata,
                    )
                )
            self._sync_section_index(
                package_name=package_name,
                ecosystem=ecosystem,
                candidate=candidate,
                metadata=metadata,
            )
            accepted += 1

        self.session.commit()
        return accepted

    def _conditional_headers(self, url: str) -> dict[str, str]:
        existing = self.session.execute(
            select(DependencyDoc).where(DependencyDoc.url == url)
        ).scalar_one_or_none()
        if existing is None:
            return {}
        metadata = existing.metadata_json or {}
        headers: dict[str, str] = {}
        etag = metadata.get("etag")
        last_modified = metadata.get("last_modified")
        if etag:
            headers["If-None-Match"] = str(etag)
        if last_modified:
            headers["If-Modified-Since"] = str(last_modified)
        return headers

    def _sync_section_index(
        self,
        package_name: str,
        ecosystem: str,
        candidate: VendorDocCandidate,
        metadata: dict[str, object],
    ) -> None:
        sections = _candidate_sections(candidate)
        source = self.session.execute(
            select(Source).where(
                Source.tenant_id == _global_tenant_id(),
                Source.repo_id.is_(None),
                Source.source_type == "vendor_doc",
                Source.path_or_url == candidate.url,
            )
        ).scalar_one_or_none()
        source_metadata = {
            "package_name": package_name,
            "ecosystem": ecosystem,
            "doc_type": candidate.doc_type,
            "version_range": candidate.version_range,
            "page_content_hash": _page_content_hash(candidate.raw_text),
            "section_index_hash": _section_index_hash(sections),
            **metadata,
        }
        if source is None:
            source = Source(
                tenant_id=_global_tenant_id(),
                repo_id=None,
                source_type="vendor_doc",
                authority="official",
                path_or_url=candidate.url,
                version_range=candidate.version_range,
                acl_scope=_vendor_doc_acl_scope(),
                metadata_json=source_metadata,
            )
            self.session.add(source)
            self.session.flush()
        else:
            existing_index_doc = self.session.execute(
                select(Document.id).where(Document.source_id == source.id).limit(1)
            ).scalar_one_or_none()
            if source.metadata_json == source_metadata and existing_index_doc is not None:
                return
            source.authority = "official"
            source.version_range = candidate.version_range
            source.acl_scope = _vendor_doc_acl_scope()
            source.metadata_json = source_metadata
            self.session.execute(delete(Document).where(Document.source_id == source.id))

        for section in sections:
            section_title = str(
                section.get("section_title")
                or section.get("heading")
                or candidate.section_title
                or candidate.title
            )
            section_text = str(section.get("raw_text") or candidate.raw_text).strip()
            if not section_text:
                continue
            section_index = int(section.get("section_index", 0))
            section_metadata = {
                **metadata,
                "package_name": package_name,
                "ecosystem": ecosystem,
                "doc_type": candidate.doc_type,
                "parent_dependency_doc_url": candidate.url,
                "section_heading": section.get("heading"),
                "section_version_heading": section.get("version_heading"),
                "section_index": section_index,
            }
            document = Document(
                tenant_id=_global_tenant_id(),
                repo_id=None,
                source_id=source.id,
                title=candidate.title,
                section_title=section_title,
                mime_type="text/html",
                language="markdown",
                checksum=_section_checksum(
                    title=candidate.title,
                    section_title=section_title,
                    raw_text=section_text,
                ),
                raw_text=section_text,
                metadata_json=section_metadata,
            )
            self.session.add(document)
            self.session.flush()

            context_prefix = _build_vendor_doc_context_prefix(
                package_name=package_name,
                ecosystem=ecosystem,
                candidate=candidate,
                section_title=section_title,
            )
            self.session.add(
                Chunk(
                    tenant_id=_global_tenant_id(),
                    repo_id=None,
                    document_id=document.id,
                    source_id=source.id,
                    chunk_index=0,
                    chunk_type="vendor_doc_section",
                    symbol_path=None,
                    text=section_text,
                    context_prefix=context_prefix,
                    token_count=max(1, len(section_text.split())),
                    embedding=embed_text(f"{context_prefix}\n{section_text}"),
                    authority="official",
                    version_range=candidate.version_range,
                    acl_scope=_vendor_doc_acl_scope(),
                    metadata_json=section_metadata,
                )
            )

    def _is_allowed_domain(self, url: str, allowed_domains: list[str]) -> bool:
        if not allowed_domains:
            return False
        hostname = (urlparse(url).hostname or "").lower()
        return any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in allowed_domains
        )

    def _discover_page_urls(
        self,
        index_url: str,
        links: list[str],
        allowed_domains: list[str],
        include_url_prefixes: list[str],
        max_pages: int,
    ) -> list[str]:
        discovered: list[str] = []
        for link in links:
            resolved = urljoin(index_url, link)
            if not self._is_allowed_domain(resolved, allowed_domains):
                continue
            if include_url_prefixes and not any(
                resolved.startswith(prefix) for prefix in include_url_prefixes
            ):
                continue
            if resolved not in discovered:
                discovered.append(resolved)
            if len(discovered) >= max_pages:
                break
        return discovered


class _SimpleHtmlDocParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.first_heading: str | None = None
        self._current_tag: str | None = None
        self._parts: list[str] = []
        self.links: list[str] = []
        self.headings: list[dict[str, str]] = []
        self.version_headings: list[str] = []
        self.sections: list[dict[str, object]] = []
        self._section_heading: str | None = None
        self._section_level: str | None = None
        self._section_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._current_tag = tag.lower()
        if self._current_tag == "a":
            for key, value in attrs:
                if key.lower() == "href" and value:
                    self.links.append(str(value))

    def handle_endtag(self, tag: str) -> None:
        self._current_tag = None

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self._current_tag == "title" and self.title is None:
            self.title = text
        if self._current_tag in {"h1", "h2"} and self.first_heading is None:
            self.first_heading = text
        if self._current_tag in {"h1", "h2", "h3"}:
            self.headings.append({"level": self._current_tag, "text": text})
            if _looks_like_version_heading(text):
                self.version_headings.append(text)
            self._start_section(level=self._current_tag, heading=text)
        elif self._section_heading is not None:
            self._section_parts.append(text)
        self._parts.append(text)

    def text_content(self) -> str:
        return "\n".join(self._parts)

    def section_payloads(self) -> list[dict[str, object]]:
        sections = list(self.sections)
        current = self._current_section_payload()
        if current is not None:
            sections.append(current)
        if sections:
            return sections
        raw_text = self.text_content().strip()
        if not raw_text:
            return []
        fallback_title = self.first_heading or self.title or "Document"
        return [
            {
                "section_title": fallback_title,
                "heading": fallback_title,
                "raw_text": raw_text,
                "section_index": 0,
                "version_heading": (
                    fallback_title
                    if _looks_like_version_heading(fallback_title)
                    else None
                ),
            }
        ]

    def _start_section(self, level: str, heading: str) -> None:
        current = self._current_section_payload()
        if current is not None:
            self.sections.append(current)
        self._section_heading = heading
        self._section_level = level
        self._section_parts = []

    def _current_section_payload(self) -> dict[str, object] | None:
        if self._section_heading is None:
            return None
        raw_text = "\n".join(self._section_parts).strip()
        if not raw_text:
            return None
        return {
            "section_title": self._section_heading,
            "heading": self._section_heading,
            "level": self._section_level,
            "raw_text": raw_text,
            "version_heading": (
                self._section_heading
                if _looks_like_version_heading(self._section_heading)
                else None
            ),
            "section_index": len(self.sections),
        }


def _infer_doc_type(
    url: str,
    title: str,
    default_doc_type: str,
    include_doc_types: list[str],
) -> str | None:
    haystack = f"{url} {title}".lower()
    candidates = include_doc_types or [default_doc_type]
    for candidate in candidates:
        normalized = candidate.replace("_", " ")
        if normalized in haystack or candidate.replace("_", "-") in haystack:
            return candidate
    if not include_doc_types:
        return default_doc_type
    return None


def _looks_like_version_heading(text: str) -> bool:
    normalized = text.strip().lower()
    return bool(
        normalized
        and (
            normalized.startswith("v")
            and any(char.isdigit() for char in normalized[1:])
            or re_search_version(normalized)
        )
    )


def re_search_version(text: str) -> bool:
    import re

    return bool(re.search(r"\b\d+\.\d+(?:\.\d+)?\b", text))


def _resolve_section_title(parser: _SimpleHtmlDocParser) -> str | None:
    if parser.version_headings:
        return parser.version_headings[0]
    return parser.first_heading


def _doc_structure_metadata(
    parser: _SimpleHtmlDocParser,
    response_headers: object | None = None,
) -> dict[str, object]:
    metadata = {
        "headings": parser.headings[:10],
        "version_headings": parser.version_headings[:10],
        "structure_kind": (
            "versioned_sections" if parser.version_headings else "flat_sections"
        ),
        "sections": parser.section_payloads(),
    }
    if response_headers is not None:
        etag = response_headers.get("etag")
        last_modified = response_headers.get("last-modified")
        if etag:
            metadata["etag"] = etag
        if last_modified:
            metadata["last_modified"] = last_modified
    return metadata


def _global_tenant_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000000")


def _scope_key(package_name: str, ecosystem: str) -> str:
    return f"{package_name}:{ecosystem}"


def _serialize_fetch_targets(requests: list[VendorDocFetchRequest]) -> str:
    return json.dumps(sorted(request.url for request in requests))


def _serialize_discovery_targets(requests: list[VendorDocDiscoveryRequest]) -> str:
    return json.dumps(sorted(request.index_url for request in requests))


def _serialize_candidate_snapshot(
    requests: list[VendorDocFetchRequest] | list[VendorDocDiscoveryRequest],
    candidates: list[VendorDocCandidate],
    mode: str,
) -> str:
    request_items: list[dict[str, object]] = []
    for request in requests:
        request_items.append(
            {
                "doc_type": getattr(request, "doc_type", None),
                "url": getattr(request, "url", None),
                "index_url": getattr(request, "index_url", None),
                "version_range": getattr(request, "version_range", None),
            }
        )

    candidate_items = [
        {
            "url": candidate.url,
            "doc_type": candidate.doc_type,
            "section_title": candidate.section_title,
            "version_range": candidate.version_range,
            "content_hash": hashlib.sha256(candidate.raw_text.encode("utf-8")).hexdigest(),
        }
        for candidate in sorted(candidates, key=lambda item: item.url)
    ]
    payload = {
        "mode": mode,
        "request_count": len(requests),
        "candidate_count": len(candidates),
        "requests": sorted(
            request_items,
            key=lambda item: (
                str(item.get("index_url") or item.get("url") or ""),
                str(item.get("doc_type") or ""),
                str(item.get("version_range") or ""),
            ),
        ),
        "candidates": candidate_items,
    }
    return json.dumps(payload, sort_keys=True)


def _candidate_sections(candidate: VendorDocCandidate) -> list[dict[str, object]]:
    metadata = getattr(candidate, "metadata_json", None) or {}
    sections = metadata.get("sections")
    if isinstance(sections, list):
        normalized_sections: list[dict[str, object]] = []
        for index, section in enumerate(sections):
            if not isinstance(section, dict):
                continue
            raw_text = str(section.get("raw_text") or "").strip()
            if not raw_text:
                continue
            normalized_sections.append(
                {
                    "section_title": section.get("section_title") or section.get("heading"),
                    "heading": section.get("heading"),
                    "raw_text": raw_text,
                    "version_heading": section.get("version_heading"),
                    "section_index": int(section.get("section_index", index)),
                }
            )
        if normalized_sections:
            return normalized_sections
    fallback_title = candidate.section_title or candidate.title
    return [
        {
            "section_title": fallback_title,
            "heading": fallback_title,
            "raw_text": candidate.raw_text,
            "version_heading": candidate.section_title if candidate.section_title else None,
            "section_index": 0,
        }
    ]


def _build_vendor_doc_context_prefix(
    package_name: str,
    ecosystem: str,
    candidate: VendorDocCandidate,
    section_title: str,
) -> str:
    lines = [
        "SourceType: vendor_doc",
        f"Package: {package_name}",
        f"Ecosystem: {ecosystem}",
        f"DocumentType: {candidate.doc_type}",
        f"Title: {candidate.title}",
        f"Section: {section_title}",
        f"URL: {candidate.url}",
    ]
    if candidate.version_range:
        lines.append(f"VersionRange: {candidate.version_range}")
    lines.append("This chunk contains official vendor documentation.")
    return "\n".join(lines)


def _section_checksum(title: str, section_title: str, raw_text: str) -> str:
    payload = "\n".join([title, section_title, raw_text])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _page_content_hash(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def _section_index_hash(sections: list[dict[str, object]]) -> str:
    payload = json.dumps(sections, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _vendor_doc_acl_scope() -> dict[str, str]:
    return {"visibility": "global"}
