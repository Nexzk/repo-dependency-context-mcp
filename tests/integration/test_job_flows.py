from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

from sqlalchemy import func, select

from repo_dependency_context_mcp.db.models import (
    DependencyDoc,
    EvalRun,
    Repo,
    Source,
    SyncCursor,
    SyncRun,
    Tenant,
)
from repo_dependency_context_mcp.services.ingest.local_repo import LocalRepoIngestService
from repo_dependency_context_mcp.workers.tasks.jobs import (
    discover_vendor_docs_task,
    fetch_vendor_docs_task,
    ingest_github_metadata_task,
    run_eval_task,
)


class _GitHubHandler(BaseHTTPRequestHandler):
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
            "/repos/acme/sample/commits": [],
            "/release-notes": """
            <html><head><title>FastAPI Release Notes</title></head>
            <body><main><h1>FastAPI Release Notes</h1>
            <p>Official migration details.</p></main></body></html>
            """.strip(),
            "/docs": """
            <html><head><title>Docs Index</title></head><body><main>
            <a href="/docs/release-notes">Release Notes</a>
            <a href="/docs/migration-guide">Migration Guide</a>
            <a href="https://example.com/community-guide">Community Guide</a>
            </main></body></html>
            """.strip(),
            "/docs/release-notes": """
            <html><head><title>FastAPI Release Notes</title></head>
            <body><main><h1>FastAPI Release Notes</h1>
            <p>Official release notes.</p></main></body></html>
            """.strip(),
            "/docs/migration-guide": """
            <html><head><title>FastAPI Migration Guide</title></head>
            <body><main><h1>FastAPI Migration Guide</h1>
            <p>Official migration guide.</p></main></body></html>
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


def test_job_tasks_execute_existing_services(db_session, tmp_path: Path) -> None:
    server = HTTPServer(("127.0.0.1", 0), _GitHubHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        tenant = Tenant(name="Tenant Jobs", slug="tenant-jobs")
        db_session.add(tenant)
        db_session.flush()

        repo_root = tmp_path / "sample_repo"
        repo_root.mkdir()
        (repo_root / "src").mkdir()
        (repo_root / "src" / "auth.py").write_text(
            "def require_admin(user):\n    return user.get('is_admin', False)\n",
            encoding="utf-8",
        )

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

        LocalRepoIngestService(db_session).ingest_repo(
            tenant_id=tenant.id,
            repo_id=repo.id,
            repo_path=repo_root,
            acl_scope={"visibility": "private"},
        )

        github_result = ingest_github_metadata_task.run(
            str(tenant.id),
            str(repo.id),
            "acme",
            "sample",
            {"visibility": "private"},
            f"http://127.0.0.1:{server.server_port}",
        )
        assert github_result["items_written"] == 1
        assert github_result["sync"]["status"] == "completed"

        vendor_result = fetch_vendor_docs_task.run(
            "fastapi",
            "python",
            {"fastapi": ["127.0.0.1"]},
            [
                {
                    "doc_type": "release_notes",
                    "url": f"http://127.0.0.1:{server.server_port}/release-notes",
                    "version_range": "0.115.x",
                }
            ],
        )
        assert vendor_result["items_written"] == 1
        assert vendor_result["sync"]["status"] == "completed"

        discovered_result = discover_vendor_docs_task.run(
            "fastapi",
            "python",
            {"fastapi": ["127.0.0.1"]},
            [
                {
                    "index_url": f"http://127.0.0.1:{server.server_port}/docs",
                    "doc_type": "release_notes",
                    "version_range": "0.115.x",
                    "include_url_prefixes": [f"http://127.0.0.1:{server.server_port}/docs/"],
                    "include_doc_types": ["release_notes", "migration_guide"],
                    "max_pages": 10,
                }
            ],
        )
        assert discovered_result["items_written"] == 2
        assert discovered_result["sync"]["status"] == "completed"

        dataset_path = tmp_path / "eval.yaml"
        dataset_path.write_text(
            f"""
name: jobs-eval
description: eval by task
cases:
  - id: locate_auth
    query: require_admin
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/auth.py
    acceptable_sources: []
    must_not_hit_sources: []
    requires_clarification: false
""".strip(),
            encoding="utf-8",
        )
        baseline_dataset_path = tmp_path / "eval_baseline.yaml"
        baseline_dataset_path.write_text(
            f"""
name: jobs-eval-baseline
description: baseline eval by task
cases:
  - id: locate_auth_baseline
    query: require_admin
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/auth.py
    acceptable_sources: []
    must_not_hit_sources: []
    requires_clarification: false
""".strip(),
            encoding="utf-8",
        )
        run_eval_task.run(str(baseline_dataset_path))

        eval_summary = run_eval_task.run(
            str(dataset_path),
            baseline_dataset_name="jobs-eval-baseline",
        )
        assert eval_summary["case_count"] == 1
        assert eval_summary["selected_eval_comparison"]["baseline_source"] == "jobs-eval-baseline"

        matrix_summary = run_eval_task.run(
            str(dataset_path),
            candidate_profiles=[
                "hybrid_dual_route_v1",
                "hybrid_dual_route_dense_boost_v1",
            ],
            rerank_profiles=["local_task_aware_v2"],
            baseline_dataset_name="jobs-eval-baseline",
        )
        assert matrix_summary["mode"] == "matrix"
        assert matrix_summary["run_count"] == 2
        assert len(matrix_summary["runs"]) == 2
        assert len(matrix_summary["comparison_table"]) == 2
        assert matrix_summary["best_run"] is not None

        assert db_session.scalar(
            select(func.count()).select_from(Source).where(Source.source_type == "pr")
        ) == 1
        assert db_session.scalar(select(func.count()).select_from(DependencyDoc)) == 3
        assert db_session.scalar(select(func.count()).select_from(EvalRun)) == 4
        assert db_session.scalar(
            select(func.count()).select_from(SyncRun).where(SyncRun.source_kind == "github_prs")
        ) == 1
        assert db_session.scalar(
            select(func.count()).select_from(SyncRun).where(SyncRun.source_kind == "vendor_docs")
        ) == 2
        assert db_session.scalar(
            select(func.count())
            .select_from(SyncCursor)
            .where(SyncCursor.source_kind == "vendor_docs")
        ) == 1
    finally:
        server.shutdown()
        server.server_close()
