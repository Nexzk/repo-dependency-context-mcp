from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from repo_dependency_context_mcp.db.models import DependencyDoc


@dataclass(slots=True)
class VendorDocCandidate:
    doc_type: str
    authority: str
    url: str
    title: str
    section_title: str | None
    raw_text: str
    version_range: str | None


@dataclass(slots=True)
class VendorDocFetchRequest:
    doc_type: str
    url: str
    version_range: str | None = None


class VendorDocIngestService:
    def __init__(self, session: Session, official_domains: dict[str, list[str]]) -> None:
        self.session = session
        self.official_domains = official_domains

    def fetch_and_ingest(self, package_name: str, ecosystem: str, requests: list[VendorDocFetchRequest]) -> int:
        candidates: list[VendorDocCandidate] = []
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
                        section_title=parser.first_heading,
                        raw_text=parser.text_content(),
                        version_range=request.version_range,
                    )
                )

        return self.ingest_candidates(
            package_name=package_name,
            ecosystem=ecosystem,
            candidates=candidates,
            ingest_source="vendor_docs_fetcher",
        )

    def ingest_candidates(
        self,
        package_name: str,
        ecosystem: str,
        candidates: list[VendorDocCandidate],
        ingest_source: str = "vendor_docs",
    ) -> int:
        allowed_domains = self.official_domains.get(package_name, [])
        accepted = 0

        for candidate in candidates:
            if not self._is_allowed_domain(candidate.url, allowed_domains):
                continue

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
                    metadata_json={"ingest_source": ingest_source},
                )
            )
            accepted += 1

        self.session.commit()
        return accepted

    def _is_allowed_domain(self, url: str, allowed_domains: list[str]) -> bool:
        if not allowed_domains:
            return False
        hostname = (urlparse(url).hostname or "").lower()
        return any(hostname == domain or hostname.endswith(f".{domain}") for domain in allowed_domains)


class _SimpleHtmlDocParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.first_heading: str | None = None
        self._current_tag: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        self._current_tag = tag.lower()

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
        self._parts.append(text)

    def text_content(self) -> str:
        return "\n".join(self._parts)
