from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from repo_dependency_context_mcp.db.models import DependencyDoc
from repo_dependency_context_mcp.services.ingest.sync_state import SyncStateService


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
            cursor_kind="request_targets",
        )
        candidates: list[VendorDocCandidate] = []
        try:
            with httpx.Client(follow_redirects=True, timeout=10.0) as client:
                for request in requests:
                    allowed_domains = self.official_domains.get(package_name, [])
                    if not self._is_allowed_domain(request.url, allowed_domains):
                        continue

                    response = client.get(request.url)
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
                            metadata_json=_doc_structure_metadata(parser),
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
                cursor_after=_serialize_fetch_targets(requests),
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
            cursor_kind="request_targets",
        )
        candidates: list[VendorDocCandidate] = []
        page_cache: dict[str, tuple[str, str | None, str] | None] = {}
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
                                page_response = client.get(page_url)
                                page_response.raise_for_status()
                            except Exception:
                                page_cache[page_url] = None
                                continue
                            page_parser = _SimpleHtmlDocParser()
                            page_parser.feed(page_response.text)
                            page_cache[page_url] = (
                                page_parser.title or page_url,
                                page_parser.first_heading,
                                page_parser.text_content(),
                            )
                        page_data = page_cache[page_url]
                        if page_data is None:
                            continue
                        page_title, section_title, raw_text = page_data
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
                                section_title=_resolve_section_title(page_parser),
                                raw_text=raw_text,
                                version_range=request.version_range,
                                metadata_json=_doc_structure_metadata(page_parser),
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
                cursor_after=_serialize_discovery_targets(requests),
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
            accepted += 1

        self.session.commit()
        return accepted

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
        self._parts.append(text)

    def text_content(self) -> str:
        return "\n".join(self._parts)


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


def _doc_structure_metadata(parser: _SimpleHtmlDocParser) -> dict[str, object]:
    return {
        "headings": parser.headings[:10],
        "version_headings": parser.version_headings[:10],
        "structure_kind": (
            "versioned_sections" if parser.version_headings else "flat_sections"
        ),
    }


def _global_tenant_id() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000000")


def _scope_key(package_name: str, ecosystem: str) -> str:
    return f"{package_name}:{ecosystem}"


def _serialize_fetch_targets(requests: list[VendorDocFetchRequest]) -> str:
    return json.dumps(sorted(request.url for request in requests))


def _serialize_discovery_targets(requests: list[VendorDocDiscoveryRequest]) -> str:
    return json.dumps(sorted(request.index_url for request in requests))
