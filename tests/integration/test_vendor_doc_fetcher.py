from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from sqlalchemy import func, select

from repo_dependency_context_mcp.db.models import DependencyDoc
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
        assert "Official migration details for FastAPI 0.115." in doc.raw_text
        assert doc.metadata_json["ingest_source"] == "vendor_docs_fetcher"
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
