from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from sqlalchemy import select

from repo_dependency_context_mcp.db.models import DependencyDoc
from repo_dependency_context_mcp.services.dependencies.vendor_docs import (
    VendorDocFetchRequest,
    VendorDocIngestService,
)


class _DocHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = """
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
""".strip()
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
