from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from sqlalchemy import select

from repo_dependency_context_mcp.db.models import Chunk, Document, Repo, Source, Tenant
from repo_dependency_context_mcp.services.ingest.github_metadata import GitHubMetadataIngestService


class _GitHubHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        routes = {
            "/repos/acme/sample/pulls": [
                {
                    "number": 101,
                    "title": "Harden admin middleware",
                    "body": "Updates require_admin in src/auth.py and related auth checks.",
                    "user": {"login": "alice"},
                    "labels": [{"name": "auth"}, {"name": "security"}],
                    "merged_at": "2026-03-20T00:00:00Z",
                }
            ],
            "/repos/acme/sample/issues": [
                {
                    "number": 77,
                    "title": "Admin route fails for privileged users",
                    "body": "Possible regression around require_admin in src/auth.py.",
                    "user": {"login": "carol"},
                    "labels": [{"name": "bug"}],
                    "pull_request": None,
                }
            ],
            "/repos/acme/sample/commits": [
                {
                    "sha": "abc123",
                    "commit": {
                        "message": "Refine require_admin guard in src/auth.py",
                        "author": {"name": "bob"},
                    }
                }
            ],
        }
        payload = json.dumps(routes.get(self.path, [])).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A003
        return


def test_github_metadata_ingest_fetches_and_persists_changes(db_session) -> None:
    server = HTTPServer(("127.0.0.1", 0), _GitHubHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        tenant = Tenant(name="Tenant GitHub", slug="tenant-github")
        db_session.add(tenant)
        db_session.flush()

        repo = Repo(
            tenant_id=tenant.id,
            name="sample-repo",
            provider="github",
            external_id="acme/sample",
            default_branch="main",
            acl_scope={"visibility": "private"},
        )
        db_session.add(repo)
        db_session.commit()

        ingested = GitHubMetadataIngestService(
            db_session,
            base_url=f"http://127.0.0.1:{server.server_port}",
            token=None,
        ).ingest_repo_changes(
            tenant_id=tenant.id,
            repo_id=repo.id,
            owner="acme",
            repo_name="sample",
            acl_scope={"visibility": "private"},
        )

        assert ingested == 3

        sources = db_session.scalars(select(Source).order_by(Source.source_type)).all()
        assert [source.source_type for source in sources] == ["commit", "issue", "pr"]

        documents = db_session.scalars(select(Document).order_by(Document.title)).all()
        assert {doc.title for doc in documents} == {
            "Admin route fails for privileged users",
            "Harden admin middleware",
            "Refine require_admin guard in src/auth.py",
        }

        chunks = db_session.scalars(select(Chunk).order_by(Chunk.chunk_type)).all()
        chunk_by_type = {chunk.chunk_type: chunk for chunk in chunks}
        for chunk in chunks:
            assert chunk.metadata_json["related_file_paths"] == ["src/auth.py"]
            assert chunk.metadata_json["related_symbols"] == ["require_admin"]

        assert chunk_by_type["pr_summary"].metadata_json["source_pr_ref"] == "pr-101"
        assert chunk_by_type["commit_summary"].metadata_json["source_commit_sha"] == "abc123"
        assert chunk_by_type["issue_summary"].metadata_json["source_issue_ref"] == "issue-77"
    finally:
        server.shutdown()
        server.server_close()
