from __future__ import annotations

import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from repo_dependency_context_mcp.db.models import DependencyDoc, SyncCursor, SyncRun
from repo_dependency_context_mcp.services.dependencies.vendor_docs import (
    VendorDocDiscoveryRequest,
    VendorDocFetchRequest,
    VendorDocIngestService,
)


class _DocHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        routes = {
            "/release-notes": """
<!doctype html>
<html>
  <head><title>FastAPI Release Notes</title></head>
  <body>
    <main>
      <h1>FastAPI Release Notes</h1>
      <h2>0.115</h2>
      <p>Official migration details for FastAPI 0.115.</p>
    </main>
  </body>
</html>
""".strip(),
            "/docs": """
<!doctype html>
<html>
  <head><title>FastAPI Docs</title></head>
  <body>
    <main>
      <h1>Docs Index</h1>
      <a href="/docs/release-notes">Release Notes</a>
      <a href="/docs/migration-guide">Migration Guide</a>
      <a href="/docs/reference-api">Reference API</a>
      <a href="https://example.com/community-guide">Community Guide</a>
    </main>
  </body>
</html>
""".strip(),
            "/docs/release-notes": """
<!doctype html>
<html>
  <head><title>FastAPI Release Notes</title></head>
  <body>
    <main>
      <h1>FastAPI Release Notes</h1>
      <p>Release notes for FastAPI 0.115.</p>
    </main>
  </body>
</html>
""".strip(),
            "/docs/migration-guide": """
<!doctype html>
<html>
  <head><title>FastAPI Migration Guide</title></head>
  <body>
    <main>
      <h1>FastAPI Migration Guide</h1>
      <p>Migration guide for FastAPI 0.115.</p>
    </main>
  </body>
</html>
""".strip(),
            "/docs/reference-api": """
<!doctype html>
<html>
  <head><title>FastAPI Reference API</title></head>
  <body>
    <main>
      <h1>Reference API</h1>
      <p>Reference material that should not be ingested as release notes or a migration guide.</p>
    </main>
  </body>
</html>
""".strip(),
        }
        body = routes[self.path]
        payload = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A003
        return


def test_vendor_doc_fetcher_fetches_whitelisted_html_and_persists(db_session) -> None:
    server = HTTPServer(("127.0.0.1", 0), _DocHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_port}/release-notes"
        service = VendorDocIngestService(
            db_session,
            official_domains={"fastapi": ["127.0.0.1"]},
        )

        accepted = service.fetch_and_ingest(
            package_name="fastapi",
            ecosystem="python",
            requests=[
                VendorDocFetchRequest(
                    doc_type="release_notes",
                    url=base_url,
                    version_range="0.115.x",
                )
            ],
        )

        assert accepted == 1
        doc = db_session.scalar(select(DependencyDoc))
        assert doc is not None
        assert doc.title == "FastAPI Release Notes"
        assert doc.section_title == "0.115"
        assert "Official migration details for FastAPI 0.115." in doc.raw_text
        assert doc.metadata_json["ingest_source"] == "vendor_docs_fetcher"
        assert doc.metadata_json["version_headings"] == ["0.115"]
        assert doc.metadata_json["structure_kind"] == "versioned_sections"

        cursor = db_session.scalar(
            select(SyncCursor).where(
                SyncCursor.source_kind == "vendor_docs",
                SyncCursor.scope_key == "fastapi:python",
            )
        )
        run = db_session.scalar(
            select(SyncRun).where(
                SyncRun.source_kind == "vendor_docs",
                SyncRun.scope_key == "fastapi:python",
            )
        )
        assert cursor is not None
        assert cursor.cursor_kind == "vendor_doc_snapshot"
        assert cursor.last_success_at is not None
        assert '"mode": "fetch"' in cursor.cursor_value
        assert '"candidate_count": 1' in cursor.cursor_value
        assert run is not None
        assert run.status == "completed"
        assert run.items_written == 1
    finally:
        server.shutdown()
        server.server_close()


def test_vendor_doc_fetcher_discovers_and_batches_multiple_whitelisted_pages(db_session) -> None:
    server = HTTPServer(("127.0.0.1", 0), _DocHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        service = VendorDocIngestService(
            db_session,
            official_domains={"fastapi": ["127.0.0.1"]},
        )

        accepted = service.discover_and_ingest(
            package_name="fastapi",
            ecosystem="python",
            requests=[
                VendorDocDiscoveryRequest(
                    index_url=f"{base_url}/docs",
                    doc_type="release_notes",
                    version_range="0.115.x",
                    include_url_prefixes=[f"{base_url}/docs/"],
                    include_doc_types=["release_notes", "migration_guide"],
                    max_pages=10,
                )
            ],
        )

        assert accepted == 2
        docs = db_session.scalars(select(DependencyDoc).order_by(DependencyDoc.url)).all()
        assert [doc.url for doc in docs] == [
            f"{base_url}/docs/migration-guide",
            f"{base_url}/docs/release-notes",
        ]
        assert all(doc.metadata_json["ingest_source"] == "vendor_docs_discovery" for doc in docs)
        assert docs[0].section_title == "FastAPI Migration Guide"
        assert docs[0].metadata_json["structure_kind"] == "flat_sections"
        assert docs[1].metadata_json["structure_kind"] == "flat_sections"

        cursor = db_session.scalar(
            select(SyncCursor).where(
                SyncCursor.source_kind == "vendor_docs",
                SyncCursor.scope_key == "fastapi:python",
            )
        )
        assert cursor is not None
        assert cursor.cursor_kind == "vendor_doc_snapshot"
        assert '"mode": "discovery"' in cursor.cursor_value
        assert '"candidate_count": 2' in cursor.cursor_value

        accepted_again = service.discover_and_ingest(
            package_name="fastapi",
            ecosystem="python",
            requests=[
                VendorDocDiscoveryRequest(
                    index_url=f"{base_url}/docs",
                    doc_type="release_notes",
                    version_range="0.115.x",
                    include_url_prefixes=[f"{base_url}/docs/"],
                    include_doc_types=["release_notes", "migration_guide"],
                    max_pages=10,
                )
            ],
        )

        assert accepted_again == 0
        assert db_session.scalar(select(func.count()).select_from(DependencyDoc)) == 2
    finally:
        server.shutdown()
        server.server_close()
def test_discover_and_ingest_deduplicates_same_batch_urls(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = {
        "https://docs.example.com/docs/index": """
        <html><body>
            <a href="/docs/changelog/v1">Release Notes</a>
            <a href="/docs/changelog/v1">Release Notes Duplicate</a>
        </body></html>
        """,
        "https://docs.example.com/docs/changelog/v1": """
        <html><head><title>Release Notes</title></head><body>
            <h1>v1 Release Notes</h1>
            <p>Important changes</p>
        </body></html>
        """,
    }
    service = VendorDocIngestService(
        db_session,
        official_domains={"fastapi": ["docs.example.com"]},
    )
    monkeypatch.setattr(
        "repo_dependency_context_mcp.services.dependencies.vendor_docs.httpx.Client",
        lambda *args, **kwargs: FakeHttpClient(responses),
    )

    result = service.discover_and_ingest(
        "fastapi",
        "python",
        [
            _make_discovery_request(
                version_range=">=0.110,<1.0",
                index_url="https://docs.example.com/docs/index",
                doc_type="release_notes",
                allowed_domains=("docs.example.com",),
                include_url_prefixes=("https://docs.example.com/docs/",),
                include_doc_types=("release_notes",),
                max_pages=10,
            )
        ],
    )

    assert result == 1
    docs = db_session.scalars(select(DependencyDoc)).all()
    assert len(docs) == 1
    assert docs[0].url == "https://docs.example.com/docs/changelog/v1"


def test_discover_and_ingest_skips_failed_pages_and_continues(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = {
        "https://docs.example.com/docs/index": """
        <html><body>
            <a href="/docs/changelog/v1">Release Notes</a>
            <a href="/docs/migration/v2">Migration Guide</a>
            <a href="/docs/changelog/missing">Missing Release Notes</a>
        </body></html>
        """,
        "https://docs.example.com/docs/changelog/v1": """
        <html><head><title>Release Notes</title></head><body>
            <h1>v1 Release Notes</h1>
            <p>Important changes</p>
        </body></html>
        """,
        "https://docs.example.com/docs/migration/v2": """
        <html><head><title>Migration Guide</title></head><body>
            <h1>v2 Migration Guide</h1>
            <p>Upgrade steps</p>
        </body></html>
        """,
    }
    service = VendorDocIngestService(
        db_session,
        official_domains={"fastapi": ["docs.example.com"]},
    )
    monkeypatch.setattr(
        "repo_dependency_context_mcp.services.dependencies.vendor_docs.httpx.Client",
        lambda *args, **kwargs: FakeHttpClient(
            responses,
            status_codes={
                "https://docs.example.com/docs/changelog/missing": 404,
            },
        ),
    )

    result = service.discover_and_ingest(
        "fastapi",
        "python",
        [
            _make_discovery_request(
                version_range=">=0.110,<1.0",
                index_url="https://docs.example.com/docs/index",
                doc_type="release_notes",
                allowed_domains=("docs.example.com",),
                include_url_prefixes=("https://docs.example.com/docs/",),
                include_doc_types=("release_notes", "migration_guide"),
                max_pages=10,
            )
        ],
    )

    assert result == 2
    docs = db_session.scalars(select(DependencyDoc)).all()
    assert {doc.url for doc in docs} == {
        "https://docs.example.com/docs/changelog/v1",
        "https://docs.example.com/docs/migration/v2",
    }


def test_ingest_candidates_deduplicates_same_batch_urls(
    db_session: Session,
) -> None:
    service = VendorDocIngestService(
        db_session,
        official_domains={"fastapi": ["docs.example.com"]},
    )

    result = service.ingest_candidates(
        "fastapi",
        "python",
        [
            _make_candidate(
                url="https://docs.example.com/docs/changelog/v1",
                doc_type="release_notes",
                version_range=">=0.110,<1.0",
                title="Release Notes",
                section_title="v1",
                raw_text="Important changes",
            ),
            _make_candidate(
                url="https://docs.example.com/docs/changelog/v1",
                doc_type="release_notes",
                version_range=">=0.110,<1.0",
                title="Release Notes",
                section_title="v1",
                raw_text="Important changes",
            ),
        ],
    )

    assert result == 1
    docs = db_session.scalars(select(DependencyDoc)).all()
    assert len(docs) == 1
    assert docs[0].url == "https://docs.example.com/docs/changelog/v1"


def test_discover_and_ingest_allows_same_page_across_request_filters(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = {
        "https://docs.example.com/docs/index": """
        <html><body>
            <a href="/docs/migration/v2">Migration Guide</a>
        </body></html>
        """,
        "https://docs.example.com/docs/migration/v2": """
        <html><head><title>Migration Guide</title></head><body>
            <h1>v2 Migration Guide</h1>
            <p>Upgrade steps</p>
        </body></html>
        """,
    }
    service = VendorDocIngestService(
        db_session,
        official_domains={"fastapi": ["docs.example.com"]},
    )
    monkeypatch.setattr(
        "repo_dependency_context_mcp.services.dependencies.vendor_docs.httpx.Client",
        lambda *args, **kwargs: FakeHttpClient(responses),
    )

    result = service.discover_and_ingest(
        "fastapi",
        "python",
        [
            _make_discovery_request(
                version_range=">=0.110,<1.0",
                index_url="https://docs.example.com/docs/index",
                doc_type="release_notes",
                include_url_prefixes=("https://docs.example.com/docs/",),
                include_doc_types=("release_notes",),
                max_pages=10,
            ),
            _make_discovery_request(
                version_range=">=0.110,<1.0",
                index_url="https://docs.example.com/docs/index",
                doc_type="release_notes",
                include_url_prefixes=("https://docs.example.com/docs/",),
                include_doc_types=("migration_guide",),
                max_pages=10,
            ),
        ],
    )

    assert result == 1
    docs = db_session.scalars(select(DependencyDoc)).all()
    assert len(docs) == 1
    assert docs[0].doc_type == "migration_guide"
    assert docs[0].url == "https://docs.example.com/docs/migration/v2"


def test_vendor_doc_failure_records_run_and_preserves_cursor(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = VendorDocIngestService(
        db_session,
        official_domains={"fastapi": ["docs.example.com"]},
    )
    existing_cursor = SyncCursor(
        tenant_id=_nil_uuid(),
        repo_id=None,
        source_kind="vendor_docs",
        scope_key="fastapi:python",
        cursor_kind="vendor_doc_snapshot",
        cursor_value='["https://docs.example.com/docs/index"]',
    )
    db_session.add(existing_cursor)
    db_session.commit()

    monkeypatch.setattr(
        "repo_dependency_context_mcp.services.dependencies.vendor_docs.httpx.Client",
        lambda *args, **kwargs: FakeHttpClient(
            {},
            status_codes={"https://docs.example.com/docs/index": 500},
        ),
    )

    with pytest.raises(RuntimeError):
        service.discover_and_ingest(
            "fastapi",
            "python",
            [
                _make_discovery_request(
                    version_range=">=0.110,<1.0",
                    index_url="https://docs.example.com/docs/index",
                    doc_type="release_notes",
                    include_url_prefixes=("https://docs.example.com/docs/",),
                    include_doc_types=("release_notes",),
                    max_pages=10,
                )
            ],
        )

    cursor = db_session.scalar(
        select(SyncCursor).where(
            SyncCursor.source_kind == "vendor_docs",
            SyncCursor.scope_key == "fastapi:python",
        )
    )
    failed_run = db_session.scalars(
        select(SyncRun)
        .where(
            SyncRun.source_kind == "vendor_docs",
            SyncRun.scope_key == "fastapi:python",
        )
        .order_by(SyncRun.created_at.desc())
    ).first()

    assert cursor is not None
    assert cursor.cursor_value == '["https://docs.example.com/docs/index"]'
    assert cursor.last_failure_at is not None
    assert failed_run is not None
    assert failed_run.status == "failed"


class FakeHttpResponse:
    def __init__(
        self,
        text: str,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHttpClient:
    def __init__(
        self,
        responses: dict[str, str],
        status_codes: dict[str, int] | None = None,
        headers_by_url: dict[str, dict[str, str]] | None = None,
        required_request_headers: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._responses = responses
        self._status_codes = status_codes or {}
        self._headers_by_url = headers_by_url or {}
        self._required_request_headers = required_request_headers or {}

    def get(self, url: str, headers: dict[str, str] | None = None) -> FakeHttpResponse:
        expected_headers = self._required_request_headers.get(url, {})
        actual_headers = headers or {}
        for key, value in expected_headers.items():
            assert actual_headers.get(key) == value
        return FakeHttpResponse(
            text=self._responses.get(url, ""),
            status_code=self._status_codes.get(url, 200),
            headers=self._headers_by_url.get(url, {}),
        )

    def __enter__(self) -> "FakeHttpClient":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def _make_discovery_request(**kwargs: object) -> object:
    return type("DiscoveryRequest", (), kwargs)()


def _make_candidate(**kwargs: object) -> object:
    return type("VendorDocCandidate", (), kwargs)()


def _nil_uuid() -> uuid.UUID:
    return uuid.UUID("00000000-0000-0000-0000-000000000000")


def test_fetch_and_ingest_uses_conditional_headers_and_skips_unchanged_docs(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = VendorDocIngestService(
        db_session,
        official_domains={"fastapi": ["docs.example.com"]},
    )
    db_session.add(
        DependencyDoc(
            package_name="fastapi",
            ecosystem="python",
            doc_type="release_notes",
            authority="official",
            url="https://docs.example.com/release-notes",
            version_range=">=0.110,<1.0",
            title="Release Notes",
            section_title="v1",
            raw_text="Existing release notes",
            metadata_json={
                "etag": "\"etag-v1\"",
                "last_modified": "Mon, 24 Mar 2026 10:00:00 GMT",
            },
        )
    )
    db_session.commit()

    monkeypatch.setattr(
        "repo_dependency_context_mcp.services.dependencies.vendor_docs.httpx.Client",
        lambda *args, **kwargs: FakeHttpClient(
            responses={"https://docs.example.com/release-notes": ""},
            status_codes={"https://docs.example.com/release-notes": 304},
            required_request_headers={
                "https://docs.example.com/release-notes": {
                    "If-None-Match": "\"etag-v1\"",
                    "If-Modified-Since": "Mon, 24 Mar 2026 10:00:00 GMT",
                }
            },
        ),
    )

    result = service.fetch_and_ingest(
        "fastapi",
        "python",
        [
            VendorDocFetchRequest(
                doc_type="release_notes",
                url="https://docs.example.com/release-notes",
                version_range=">=0.110,<1.0",
            )
        ],
    )

    assert result == 0
    docs = db_session.scalars(select(DependencyDoc)).all()
    assert len(docs) == 1
    assert docs[0].raw_text == "Existing release notes"
