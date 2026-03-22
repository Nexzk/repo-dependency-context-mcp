from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

from sqlalchemy import func, select

from repo_dependency_context_mcp.db.models import Chunk, DependencyDoc, IngestJob, Repo, Source, Tenant
from repo_dependency_context_mcp.services.dependencies.vendor_docs import VendorDocFetchRequest, VendorDocIngestService
from repo_dependency_context_mcp.services.ingest.github_metadata import GitHubMetadataIngestService
from repo_dependency_context_mcp.services.ingest.local_repo import LocalRepoIngestService


class _IdempotentGitHubHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        routes = {
            "/repos/acme/sample/pulls": [
                {
                    "number": 101,
                    "title": "Harden admin middleware",
                    "body": "Updates require_admin and related auth checks.",
                    "user": {"login": "alice"},
                    "labels": [{"name": "auth"}],
                    "merged_at": "2026-03-20T00:00:00Z",
                }
            ],
            "/repos/acme/sample/issues": [],
            "/repos/acme/sample/commits": [
                {
                    "sha": "abc123",
                    "commit": {
                        "message": "Refine require_admin guard",
                        "author": {"name": "bob"},
                    },
                }
            ],
            "/release-notes": "<html><head><title>FastAPI Release Notes</title></head><body><main><h1>FastAPI Release Notes</h1><p>Official migration details.</p></main></body></html>",
        }
        route = routes.get(self.path)
        if isinstance(route, str):
            payload = route.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        else:
            payload = json.dumps(route or []).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A003
        return


def test_sync_flows_are_idempotent(db_session, tmp_path: Path) -> None:
    repo_root = tmp_path / "sample_repo"
    repo_root.mkdir()
    (repo_root / "src").mkdir()
    (repo_root / "src" / "auth.py").write_text(
        "def require_admin(user):\n    return user.get('is_admin', False)\n",
        encoding="utf-8",
    )

    tenant = Tenant(name="Tenant Idempotent", slug="tenant-idempotent")
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

    repo_ingest = LocalRepoIngestService(db_session)
    first = repo_ingest.ingest_repo(
        tenant_id=tenant.id,
        repo_id=repo.id,
        repo_path=repo_root,
        acl_scope={"visibility": "private"},
    )
    second = repo_ingest.ingest_repo(
        tenant_id=tenant.id,
        repo_id=repo.id,
        repo_path=repo_root,
        acl_scope={"visibility": "private"},
    )

    assert first.source_count == 1
    assert second.source_count == 0
    assert db_session.scalar(select(func.count()).select_from(Source).where(Source.repo_id == repo.id)) == 1
    assert db_session.scalar(select(func.count()).select_from(Chunk).where(Chunk.repo_id == repo.id)) == 1
    assert db_session.scalar(select(func.count()).select_from(IngestJob)) == 2

    server = HTTPServer(("127.0.0.1", 0), _IdempotentGitHubHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        github_ingest = GitHubMetadataIngestService(
            db_session,
            base_url=f"http://127.0.0.1:{server.server_port}",
            token=None,
        )
        first_github = github_ingest.ingest_repo_changes(
            tenant_id=tenant.id,
            repo_id=repo.id,
            owner="acme",
            repo_name="sample",
            acl_scope={"visibility": "private"},
        )
        second_github = github_ingest.ingest_repo_changes(
            tenant_id=tenant.id,
            repo_id=repo.id,
            owner="acme",
            repo_name="sample",
            acl_scope={"visibility": "private"},
        )

        assert first_github == 2
        assert second_github == 0

        vendor_ingest = VendorDocIngestService(
            db_session,
            official_domains={"fastapi": ["127.0.0.1"]},
        )
        first_vendor = vendor_ingest.fetch_and_ingest(
            package_name="fastapi",
            ecosystem="python",
            requests=[
                VendorDocFetchRequest(
                    doc_type="release_notes",
                    url=f"http://127.0.0.1:{server.server_port}/release-notes",
                    version_range="0.115.x",
                )
            ],
        )
        second_vendor = vendor_ingest.fetch_and_ingest(
            package_name="fastapi",
            ecosystem="python",
            requests=[
                VendorDocFetchRequest(
                    doc_type="release_notes",
                    url=f"http://127.0.0.1:{server.server_port}/release-notes",
                    version_range="0.115.x",
                )
            ],
        )

        assert first_vendor == 1
        assert second_vendor == 0
        assert db_session.scalar(select(func.count()).select_from(DependencyDoc)) == 1
    finally:
        server.shutdown()
        server.server_close()
