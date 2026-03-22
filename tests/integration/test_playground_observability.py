from pathlib import Path

from fastapi.testclient import TestClient

from repo_dependency_context_mcp.db.models import Repo, Tenant
from repo_dependency_context_mcp.main import app
from repo_dependency_context_mcp.services.eval.runner import EvalRunnerService
from repo_dependency_context_mcp.services.ingest.local_repo import LocalRepoIngestService


def test_playground_and_metrics_endpoints_are_available(db_session, tmp_path: Path) -> None:
    repo_root = tmp_path / "sample_repo"
    repo_root.mkdir()
    (repo_root / "src").mkdir()
    (repo_root / "src" / "auth.py").write_text(
        "\n".join(
            [
                "def require_admin(user):",
                "    if not user.get('is_admin'):",
                "        raise PermissionError('admin only')",
                "    return True",
            ]
        ),
        encoding="utf-8",
    )

    tenant = Tenant(name="Tenant Obs", slug="tenant-obs")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo",
        provider="local",
        external_id="sample-repo-obs",
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

    dataset_path = tmp_path / "eval.yaml"
    dataset_path.write_text(
        f"""
name: obs-eval
description: observability eval dataset
cases:
  - id: locate_auth
    query: where is admin authorization logic
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
    EvalRunnerService(db_session).run_from_yaml(dataset_path)

    client = TestClient(app)

    playground = client.get("/playground")
    assert playground.status_code == 200
    assert "Repo + Dependency Context MCP" in playground.text

    metrics = client.get("/api/observability/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["ingest_jobs"] >= 1
    assert metrics.json()["query_logs"] >= 1
    assert metrics.json()["eval_runs"] >= 1
    assert "latest_sync_runs" in metrics.json()
    assert "latest_sync_cursors" in metrics.json()


def test_metrics_exposes_latest_eval_failure_diagnostics(
    db_session,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "sample_repo_diag"
    repo_root.mkdir()
    (repo_root / "src").mkdir()
    (repo_root / "src" / "auth.py").write_text(
        "\n".join(
            [
                "def require_admin(user):",
                "    if not user.get('is_admin'):",
                "        raise PermissionError('admin only')",
                "    return True",
            ]
        ),
        encoding="utf-8",
    )

    tenant = Tenant(name="Tenant Obs Diag", slug="tenant-obs-diag")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo-diag",
        provider="local",
        external_id="sample-repo-diag",
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

    dataset_path = tmp_path / "eval_diag.yaml"
    dataset_path.write_text(
        f"""
name: obs-eval-diagnostics
description: observability eval diagnostics dataset
cases:
  - id: missing_auth
    query: where is admin authorization logic
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/missing.py
    expected_top_source: repo_code:src/missing.py
    requires_clarification: false
""".strip(),
        encoding="utf-8",
    )
    EvalRunnerService(db_session).run_from_yaml(dataset_path)

    client = TestClient(app)
    metrics = client.get("/api/observability/metrics")

    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload["latest_eval_runs"]
    assert payload["latest_eval_runs"][0]["failed_case_count"] >= 1
    assert "must_hit_sources" in payload["latest_eval_runs"][0]["failing_checks"]
    assert payload["latest_eval_failures"]
    latest_failure = payload["latest_eval_failures"][0]
    assert latest_failure["case_name"] == "missing_auth"
    assert latest_failure["failed_checks"]
    assert latest_failure["failed_checks"][0]["check"] in {
        "must_hit_sources",
        "top_source_ok",
    }
    assert latest_failure["top_evidence_sources"]

    playground = client.get("/playground")
    assert playground.status_code == 200
    assert "Latest Eval" in playground.text
    assert "missing_auth" in playground.text
    assert "must_hit_sources" in playground.text


def test_metrics_aggregates_recent_eval_failure_checks(
    db_session,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "sample_repo_agg"
    repo_root.mkdir()
    (repo_root / "src").mkdir()
    (repo_root / "src" / "auth.py").write_text(
        "\n".join(
            [
                "def require_admin(user):",
                "    if not user.get('is_admin'):",
                "        raise PermissionError('admin only')",
                "    return True",
            ]
        ),
        encoding="utf-8",
    )

    tenant = Tenant(name="Tenant Obs Agg", slug="tenant-obs-agg")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo-agg",
        provider="local",
        external_id="sample-repo-agg",
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

    first_dataset = tmp_path / "eval_first.yaml"
    first_dataset.write_text(
        f"""
name: obs-eval-first
description: first failing eval
cases:
  - id: missing_auth
    query: where is admin authorization logic
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/missing.py
    expected_top_source: repo_code:src/missing.py
""".strip(),
        encoding="utf-8",
    )
    EvalRunnerService(db_session).run_from_yaml(first_dataset)

    second_dataset = tmp_path / "eval_second.yaml"
    second_dataset.write_text(
        f"""
name: obs-eval-second
description: second failing eval
cases:
  - id: top_source_wrong
    query: where is admin authorization logic
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/auth.py
    expected_top_source: repo_doc:docs/auth.md
""".strip(),
        encoding="utf-8",
    )
    EvalRunnerService(db_session).run_from_yaml(second_dataset)

    client = TestClient(app)
    metrics = client.get("/api/observability/metrics")

    assert metrics.status_code == 200
    payload = metrics.json()
    assert payload["recent_eval_window"] >= 2
    assert payload["recent_eval_failed_cases"] >= 2
    assert payload["recent_eval_check_failures"]["top_source_ok"] >= 2
    assert payload["recent_eval_check_failures"]["must_hit_sources"] >= 1


def test_metrics_exposes_recent_eval_score_trend(
    db_session,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "sample_repo_trend"
    repo_root.mkdir()
    (repo_root / "src").mkdir()
    (repo_root / "src" / "auth.py").write_text(
        "\n".join(
            [
                "def require_admin(user):",
                "    if not user.get('is_admin'):",
                "        raise PermissionError('admin only')",
                "    return True",
            ]
        ),
        encoding="utf-8",
    )

    tenant = Tenant(name="Tenant Obs Trend", slug="tenant-obs-trend")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo-trend",
        provider="local",
        external_id="sample-repo-trend",
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

    success_dataset = tmp_path / "eval_success.yaml"
    success_dataset.write_text(
        f"""
name: obs-eval-success
description: successful eval
cases:
  - id: locate_auth
    query: where is admin authorization logic
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/auth.py
""".strip(),
        encoding="utf-8",
    )
    EvalRunnerService(db_session).run_from_yaml(success_dataset)

    failure_dataset = tmp_path / "eval_failure.yaml"
    failure_dataset.write_text(
        f"""
name: obs-eval-failure
description: failing eval
cases:
  - id: missing_auth
    query: where is admin authorization logic
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/missing.py
    expected_top_source: repo_code:src/missing.py
""".strip(),
        encoding="utf-8",
    )
    EvalRunnerService(db_session).run_from_yaml(failure_dataset)

    client = TestClient(app)
    metrics = client.get("/api/observability/metrics")

    assert metrics.status_code == 200
    payload = metrics.json()
    assert len(payload["recent_eval_score_trend"]) >= 2
    assert payload["recent_eval_score_summary"]["window"] >= 2
    assert isinstance(payload["recent_eval_score_summary"]["avg_overall_score"], float)
    assert isinstance(payload["recent_eval_score_summary"]["avg_retrieval_score"], float)
    assert isinstance(
        payload["recent_eval_score_summary"]["avg_evidence_contract_score"],
        float,
    )
