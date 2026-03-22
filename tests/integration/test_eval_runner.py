from pathlib import Path

from sqlalchemy import select

from repo_dependency_context_mcp.db.models import EvalCaseResult, EvalRun, Repo, Tenant
from repo_dependency_context_mcp.services.eval.runner import EvalRunnerService
from repo_dependency_context_mcp.services.ingest.local_repo import LocalRepoIngestService


def test_eval_runner_executes_cases_and_persists_metrics(db_session, tmp_path: Path) -> None:
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

    tenant = Tenant(name="Tenant Eval", slug="tenant-eval")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo",
        provider="local",
        external_id="sample-repo-eval",
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
name: demo-eval
description: minimal eval dataset
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

    summary = EvalRunnerService(db_session).run_from_yaml(dataset_path)

    assert summary["case_count"] == 1
    assert summary["recall_at_5"] == 1.0
    assert summary["mrr"] == 1.0

    eval_run = db_session.scalar(select(EvalRun))
    assert eval_run is not None
    assert eval_run.status == "completed"

    case_result = db_session.scalar(select(EvalCaseResult))
    assert case_result is not None
    assert case_result.recall_at_k == 1.0
    assert case_result.mrr == 1.0
    assert case_result.leakage_count == 0
