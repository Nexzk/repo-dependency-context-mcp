from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from sqlalchemy import func, select

from repo_dependency_context_mcp.db.models import (
    Chunk,
    Document,
    Repo,
    Source,
    SyncCursor,
    SyncRun,
    Tenant,
)
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
                    "updated_at": "2026-03-20T12:00:00Z",
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
                    "updated_at": "2026-03-20T13:00:00Z",
                    "pull_request": None,
                }
            ],
            "/repos/acme/sample/commits": [
                {
                    "sha": "abc123",
                    "commit": {
                        "message": "Refine require_admin guard in src/auth.py",
                        "author": {"name": "bob", "date": "2026-03-20T14:00:00Z"},
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


def test_github_metadata_ingest_advances_sync_cursors_and_skips_old_items(db_session) -> None:
    server = HTTPServer(("127.0.0.1", 0), _GitHubHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        tenant = Tenant(name="Tenant GitHub Sync", slug="tenant-github-sync")
        db_session.add(tenant)
        db_session.flush()

        repo = Repo(
            tenant_id=tenant.id,
            name="sample-repo-sync",
            provider="github",
            external_id="acme/sample-sync",
            default_branch="main",
            acl_scope={"visibility": "private"},
        )
        db_session.add(repo)
        db_session.commit()

        service = GitHubMetadataIngestService(
            db_session,
            base_url=f"http://127.0.0.1:{server.server_port}",
            token=None,
        )

        first_ingested = service.ingest_repo_changes(
            tenant_id=tenant.id,
            repo_id=repo.id,
            owner="acme",
            repo_name="sample",
            acl_scope={"visibility": "private"},
        )
        second_ingested = service.ingest_repo_changes(
            tenant_id=tenant.id,
            repo_id=repo.id,
            owner="acme",
            repo_name="sample",
            acl_scope={"visibility": "private"},
        )

        assert first_ingested == 3
        assert second_ingested == 0

        source_count = db_session.scalar(select(func.count()).select_from(Source))
        assert source_count == 3

        cursors = db_session.scalars(
            select(SyncCursor).where(SyncCursor.repo_id == repo.id).order_by(SyncCursor.source_kind)
        ).all()
        assert [(cursor.source_kind, cursor.cursor_value) for cursor in cursors] == [
            ("github_commits", "2026-03-20T14:00:00Z"),
            ("github_issues", "2026-03-20T13:00:00Z"),
            ("github_prs", "2026-03-20T12:00:00Z"),
        ]

        runs = db_session.scalars(
            select(SyncRun)
            .where(SyncRun.repo_id == repo.id)
            .order_by(SyncRun.source_kind, SyncRun.created_at)
        ).all()
        assert len(runs) == 6
        assert all(run.status == "completed" for run in runs)

    finally:
        server.shutdown()
        server.server_close()


class _FailingGitHubHandler(_GitHubHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/repos/acme/sample/pulls":
            self.send_response(500)
            self.end_headers()
            return
        super().do_GET()


def test_github_metadata_ingest_failure_does_not_advance_cursor(db_session) -> None:
    success_server = HTTPServer(("127.0.0.1", 0), _GitHubHandler)
    success_thread = Thread(target=success_server.serve_forever, daemon=True)
    success_thread.start()

    failing_server = HTTPServer(("127.0.0.1", 0), _FailingGitHubHandler)
    failing_thread = Thread(target=failing_server.serve_forever, daemon=True)
    failing_thread.start()

    try:
        tenant = Tenant(name="Tenant GitHub Failure", slug="tenant-github-failure")
        db_session.add(tenant)
        db_session.flush()

        repo = Repo(
            tenant_id=tenant.id,
            name="sample-repo-failure",
            provider="github",
            external_id="acme/sample-failure",
            default_branch="main",
            acl_scope={"visibility": "private"},
        )
        db_session.add(repo)
        db_session.commit()

        GitHubMetadataIngestService(
            db_session,
            base_url=f"http://127.0.0.1:{success_server.server_port}",
            token=None,
        ).ingest_repo_changes(
            tenant_id=tenant.id,
            repo_id=repo.id,
            owner="acme",
            repo_name="sample",
            acl_scope={"visibility": "private"},
        )

        previous_cursor = db_session.scalar(
            select(SyncCursor.cursor_value).where(
                SyncCursor.repo_id == repo.id,
                SyncCursor.source_kind == "github_prs",
            )
        )

        try:
            GitHubMetadataIngestService(
                db_session,
                base_url=f"http://127.0.0.1:{failing_server.server_port}",
                token=None,
            ).ingest_repo_changes(
                tenant_id=tenant.id,
                repo_id=repo.id,
                owner="acme",
                repo_name="sample",
                acl_scope={"visibility": "private"},
            )
        except Exception:
            pass

        current_cursor = db_session.scalar(
            select(SyncCursor.cursor_value).where(
                SyncCursor.repo_id == repo.id,
                SyncCursor.source_kind == "github_prs",
            )
        )
        failed_run = db_session.scalars(
            select(SyncRun)
            .where(
                SyncRun.repo_id == repo.id,
                SyncRun.source_kind == "github_prs",
            )
            .order_by(SyncRun.created_at.desc())
        ).first()

        assert current_cursor == previous_cursor
        assert failed_run is not None
        assert failed_run.status == "failed"
        assert failed_run.cursor_before == previous_cursor
    finally:
        success_server.shutdown()
        success_server.server_close()
        failing_server.shutdown()
        failing_server.server_close()
