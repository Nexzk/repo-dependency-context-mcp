from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

from sqlalchemy import func, select

from repo_dependency_context_mcp.db.models import (
    Chunk,
    DependencyDoc,
    IngestJob,
    Repo,
    Source,
    SyncCursor,
    SyncRun,
    Tenant,
)
from repo_dependency_context_mcp.services.dependencies.vendor_docs import (
    VendorDocFetchRequest,
    VendorDocIngestService,
)
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
            "/release-notes": """
            <html><head><title>FastAPI Release Notes</title></head>
            <body><main><h1>FastAPI Release Notes</h1>
            <p>Official migration details.</p></main></body></html>
            """.strip(),
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
    assert db_session.scalar(
        select(func.count()).select_from(Source).where(Source.repo_id == repo.id)
    ) == 1
    assert db_session.scalar(
        select(func.count()).select_from(Chunk).where(Chunk.repo_id == repo.id)
    ) == 1
    assert db_session.scalar(select(func.count()).select_from(IngestJob)) == 2
    assert db_session.scalar(
        select(func.count()).select_from(SyncRun).where(SyncRun.source_kind == "local_repo")
    ) == 2
    local_cursor = db_session.scalar(
        select(SyncCursor).where(
            SyncCursor.repo_id == repo.id,
            SyncCursor.source_kind == "local_repo",
        )
    )
    assert local_cursor is not None
    assert local_cursor.cursor_value is not None

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


def test_local_repo_sync_failure_does_not_advance_cursor(
    db_session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "sample_repo_failure"
    repo_root.mkdir()
    (repo_root / "src").mkdir()
    (repo_root / "src" / "auth.py").write_text(
        "def require_admin(user):\n    return user.get('is_admin', False)\n",
        encoding="utf-8",
    )

    tenant = Tenant(name="Tenant Local Sync Failure", slug="tenant-local-sync-failure")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo-failure",
        provider="local",
        external_id="sample-repo-failure",
        default_branch="main",
        acl_scope={"visibility": "private"},
    )
    db_session.add(repo)
    db_session.commit()

    service = LocalRepoIngestService(db_session)
    service.ingest_repo(
        tenant_id=tenant.id,
        repo_id=repo.id,
        repo_path=repo_root,
        acl_scope={"visibility": "private"},
    )
    previous_cursor = db_session.scalar(
        select(SyncCursor.cursor_value).where(
            SyncCursor.repo_id == repo.id,
            SyncCursor.source_kind == "local_repo",
        )
    )
    (repo_root / "src" / "auth.py").write_text(
        "def require_admin(user):\n    raise PermissionError('admin only')\n",
        encoding="utf-8",
    )

    def _boom(*args, **kwargs):
        raise RuntimeError("chunk failed")

    monkeypatch.setattr(
        "repo_dependency_context_mcp.services.ingest.local_repo._chunk_file",
        _boom,
    )

    try:
        service.ingest_repo(
            tenant_id=tenant.id,
            repo_id=repo.id,
            repo_path=repo_root,
            acl_scope={"visibility": "private"},
        )
    except RuntimeError:
        pass

    current_cursor = db_session.scalar(
        select(SyncCursor.cursor_value).where(
            SyncCursor.repo_id == repo.id,
            SyncCursor.source_kind == "local_repo",
        )
    )
    failed_run = db_session.scalars(
        select(SyncRun)
        .where(
            SyncRun.repo_id == repo.id,
            SyncRun.source_kind == "local_repo",
            SyncRun.status == "failed",
        )
        .order_by(SyncRun.created_at.desc())
    ).first()

    assert current_cursor == previous_cursor
    assert failed_run is not None
    assert failed_run.status == "failed"
