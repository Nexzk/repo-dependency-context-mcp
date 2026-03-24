from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from repo_dependency_context_mcp.db.models import (
    EvalCase,
    EvalCaseResult,
    EvalRun,
    Repo,
    Tenant,
)
from repo_dependency_context_mcp.main import app
from repo_dependency_context_mcp.services.dependencies.parser import DependencyParserService
from repo_dependency_context_mcp.services.dependencies.vendor_docs import (
    VendorDocCandidate,
    VendorDocIngestService,
)
from repo_dependency_context_mcp.services.eval.runner import EvalRunnerService
from repo_dependency_context_mcp.services.ingest.change_metadata import (
    ChangeMetadataIngestService,
)
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


def test_eval_runner_returns_baseline_comparison_when_requested(
    db_session,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "sample_repo_eval_baseline"
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

    tenant = Tenant(name="Tenant Eval Baseline", slug="tenant-eval-baseline")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo-eval-baseline",
        provider="local",
        external_id="sample-repo-eval-baseline",
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

    baseline_dataset = tmp_path / "eval_runner_baseline.yaml"
    baseline_dataset.write_text(
        f"""
name: runner-baseline-dataset
description: baseline eval
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
    EvalRunnerService(db_session).run_from_yaml(baseline_dataset)

    current_dataset = tmp_path / "eval_runner_current.yaml"
    current_dataset.write_text(
        f"""
name: runner-current-dataset
description: failing current eval
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

    summary = EvalRunnerService(db_session).run_from_yaml(
        current_dataset,
        baseline_dataset_name="runner-baseline-dataset",
    )

    comparison = summary["selected_eval_comparison"]
    assert comparison["baseline_source"] == "runner-baseline-dataset"
    assert comparison["delta_overall_score"] < 0
    assert comparison["delta_failed_case_count"] > 0


def test_eval_api_returns_baseline_comparison_when_requested(
    db_session,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "sample_repo_eval_api_baseline"
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

    tenant = Tenant(name="Tenant Eval API Baseline", slug="tenant-eval-api-baseline")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo-eval-api-baseline",
        provider="local",
        external_id="sample-repo-eval-api-baseline",
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

    baseline_dataset = tmp_path / "eval_api_baseline.yaml"
    baseline_dataset.write_text(
        f"""
name: api-baseline-dataset
description: baseline eval
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
    EvalRunnerService(db_session).run_from_yaml(baseline_dataset)

    current_dataset = tmp_path / "eval_api_current.yaml"
    current_dataset.write_text(
        f"""
name: api-current-dataset
description: failing current eval
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

    client = TestClient(app)
    response = client.post(
        "/api/eval/run",
        json={
            "dataset_path": str(current_dataset),
            "baseline_dataset_name": "api-baseline-dataset",
        },
    )

    assert response.status_code == 200
    comparison = response.json()["selected_eval_comparison"]
    assert comparison["baseline_source"] == "api-baseline-dataset"
    assert comparison["delta_overall_score"] < 0


def test_eval_api_supports_profile_matrix_runs(
    db_session,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "sample_repo_eval_matrix"
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

    tenant = Tenant(name="Tenant Eval Matrix", slug="tenant-eval-matrix")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo-eval-matrix",
        provider="local",
        external_id="sample-repo-eval-matrix",
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

    dataset_path = tmp_path / "eval_matrix.yaml"
    dataset_path.write_text(
        f"""
name: api-matrix-dataset
description: eval matrix dataset
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

    client = TestClient(app)
    response = client.post(
        "/api/eval/run",
        json={
            "dataset_path": str(dataset_path),
            "candidate_profiles": [
                "hybrid_dual_route_v1",
                "hybrid_dual_route_dense_boost_v1",
            ],
            "rerank_profiles": ["local_task_aware_v2"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "matrix"
    assert payload["run_count"] == 2
    assert len(payload["runs"]) == 2
    assert len(payload["comparison_table"]) == 2
    assert payload["best_run"] is not None
    assert db_session.scalar(select(func.count()).select_from(EvalRun)) == 2


def test_eval_runner_profile_matrix_includes_baseline_deltas(
    db_session,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "sample_repo_eval_matrix_baseline"
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

    tenant = Tenant(
        name="Tenant Eval Matrix Baseline",
        slug="tenant-eval-matrix-baseline",
    )
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo-eval-matrix-baseline",
        provider="local",
        external_id="sample-repo-eval-matrix-baseline",
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

    baseline_dataset = tmp_path / "eval_matrix_baseline_base.yaml"
    baseline_dataset.write_text(
        f"""
name: matrix-baseline-base
description: baseline eval for matrix
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
    EvalRunnerService(db_session).run_from_yaml(baseline_dataset)

    current_dataset = tmp_path / "eval_matrix_baseline_current.yaml"
    current_dataset.write_text(
        f"""
name: matrix-baseline-current
description: current eval for matrix comparison
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

    matrix_result = EvalRunnerService(db_session).run_profile_matrix(
        current_dataset,
        candidate_profiles=[
            "hybrid_dual_route_v1",
            "hybrid_dual_route_dense_boost_v1",
        ],
        rerank_profiles=["local_task_aware_v2"],
        baseline_dataset_name="matrix-baseline-base",
    )

    assert matrix_result["mode"] == "matrix"
    assert matrix_result["run_count"] == 2
    assert len(matrix_result["comparison_table"]) == 2
    for row in matrix_result["comparison_table"]:
        assert row["baseline_source"] == "matrix-baseline-base"
        assert "delta_overall_score" in row
        assert "delta_retrieval_score" in row
        assert "delta_evidence_contract_score" in row
        assert "delta_failed_case_count" in row

    best_run = matrix_result["best_run"]
    assert best_run is not None
    assert "selected_eval_comparison" in best_run["summary"]
    assert (
        best_run["summary"]["selected_eval_comparison"]["baseline_source"]
        == "matrix-baseline-base"
    )


def test_eval_runner_scores_evidence_contract_fields(db_session, tmp_path: Path) -> None:
    repo_root = tmp_path / "sample_repo_contract"
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

    tenant = Tenant(name="Tenant Eval Contract", slug="tenant-eval-contract")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo-contract",
        provider="local",
        external_id="sample-repo-contract",
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
    dataset_path = tmp_path / "eval_contract.yaml"
    dataset_path.write_text(
        f"""
name: contract-eval
description: eval retrieval and evidence contract
cases:
  - id: locate_auth_contract
    query: where is admin authorization logic
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/auth.py
    acceptable_sources: []
    must_not_hit_sources: []
    expected_authorities:
      - repo
    expected_why_selected_contains:
      - signal
    expected_freshness_contains:
      - repository content
    min_evidence_count: 1
    max_evidence_count: 5
    requires_clarification: false
""".strip(),
        encoding="utf-8",
    )

    summary = EvalRunnerService(db_session).run_from_yaml(dataset_path)
    case_result = db_session.scalar(select(EvalCaseResult))

    assert summary["case_count"] == 1
    assert summary["retrieval_score"] == 1.0
    assert case_result is not None
    assert (
        case_result.result_payload["scores"]["authority_match"] == 1.0
    ), case_result.result_payload
    assert (
        case_result.result_payload["scores"]["evidence_count_ok"] == 1.0
    ), case_result.result_payload
    assert (
        case_result.result_payload["scores"]["why_selected_match"] == 1.0
    ), case_result.result_payload
    assert (
        case_result.result_payload["scores"]["freshness_reason_match"] == 1.0
    ), case_result.result_payload
    assert summary["evidence_contract_score"] == 1.0
    assert summary["overall_score"] == 1.0


def test_eval_runner_scores_source_rank_order_constraints(
    db_session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    freshness_reason = (
        "Freshness: repository content from latest local ingest snapshot"
    )
    tenant = Tenant(name="Tenant Eval Rank", slug="tenant-eval-rank")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo-rank-order",
        provider="local",
        external_id="sample-repo-rank-order",
        default_branch="main",
        acl_scope={"visibility": "private"},
    )
    db_session.add(repo)
    db_session.commit()

    evidence_by_query = {
        "rank ok query": [
            {
                "source_type": "repo_code",
                "path_or_url": "src/auth.py",
                "authority": "repo",
                "freshness_reason": freshness_reason,
                "why_selected": "Signal: lexical match",
            },
            {
                "source_type": "repo_doc",
                "path_or_url": "docs/auth.md",
                "authority": "repo",
                "freshness_reason": freshness_reason,
                "why_selected": "Signal: lexical match",
            },
        ],
        "rank bad query": [
            {
                "source_type": "repo_doc",
                "path_or_url": "docs/auth.md",
                "authority": "repo",
                "freshness_reason": freshness_reason,
                "why_selected": "Signal: lexical match",
            },
            {
                "source_type": "repo_code",
                "path_or_url": "src/auth.py",
                "authority": "repo",
                "freshness_reason": freshness_reason,
                "why_selected": "Signal: lexical match",
            },
        ],
    }

    runner = EvalRunnerService(db_session)
    monkeypatch.setattr(
        runner.tool_service,
        "search_context",
        lambda tenant_id, repo_id, query, task_type, top_k: {
            "evidence": evidence_by_query[query],
        },
    )

    dataset_path = tmp_path / "eval_rank_order.yaml"
    dataset_path.write_text(
        f"""
name: rank-order-eval
description: eval source-rank order contract
cases:
  - id: locate_auth_rank_order_ok
    query: rank ok query
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/auth.py
    must_rank_before:
      - higher: repo_code:src/auth.py
        lower: repo_doc:docs/auth.md
  - id: locate_auth_rank_order_bad
    query: rank bad query
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/auth.py
    must_rank_before:
      - higher: repo_code:src/auth.py
        lower: repo_doc:docs/auth.md
""".strip(),
        encoding="utf-8",
    )

    summary = runner.run_from_yaml(dataset_path)
    eval_cases = {
        case.id: case.name for case in db_session.scalars(select(EvalCase)).all()
    }
    case_results = {
        eval_cases[result.eval_case_id]: result
        for result in db_session.scalars(select(EvalCaseResult)).all()
    }

    assert len(case_results) == 2
    assert (
        case_results["locate_auth_rank_order_ok"].result_payload["scores"]["rank_order_ok"]
        == 1.0
    )
    assert (
        case_results["locate_auth_rank_order_bad"].result_payload["scores"]["rank_order_ok"]
        == 0.0
    )
    assert (
        case_results["locate_auth_rank_order_ok"].result_payload["scores"]["evidence_contract_score"]
        == 1.0
    )
    assert (
        case_results["locate_auth_rank_order_bad"].result_payload["scores"]["evidence_contract_score"]
        < 1.0
    )
    assert summary["evidence_contract_score"] == pytest.approx(11 / 12)


def test_eval_runner_covers_repo_dependency_and_related_change_cases(
    db_session,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "sample_repo_eval_coverage"
    repo_root.mkdir()
    (repo_root / "src").mkdir()
    (repo_root / "docs").mkdir()
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
    (repo_root / "docs" / "auth.md").write_text(
        "\n".join(
            [
                "# Authentication",
                "",
                "The require_admin helper protects admin-only routes.",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "docs" / "fastapi-upgrade-notes.md").write_text(
        "\n".join(
            [
                "# FastAPI Upgrade Notes",
                "",
                "Internal migration note for FastAPI.",
                "",
                "This older internal note still references pre-0.115 migration guidance.",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "requirements.txt").write_text(
        "fastapi==0.115.0\n",
        encoding="utf-8",
    )

    tenant = Tenant(name="Tenant Eval Coverage", slug="tenant-eval-coverage")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo-eval-coverage",
        provider="local",
        external_id="sample-repo-eval-coverage",
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
    DependencyParserService(db_session).parse_and_persist(
        tenant_id=tenant.id,
        repo_id=repo.id,
        repo_path=repo_root,
    )
    VendorDocIngestService(
        db_session,
        official_domains={"fastapi": ["fastapi.tiangolo.com"]},
    ).ingest_candidates(
        package_name="fastapi",
        ecosystem="python",
        candidates=[
            VendorDocCandidate(
                doc_type="migration_guide",
                authority="official",
                url="https://fastapi.tiangolo.com/release-notes/",
                title="FastAPI Release Notes",
                section_title="0.115",
                raw_text="FastAPI migration guide for 0.115 covers migration steps.",
                version_range="0.115.x",
            )
        ],
    )

    changes_fixture = tmp_path / "changes_eval_coverage.json"
    changes_fixture.write_text(
        """
[
  {
    "source_type": "pr",
    "external_ref": "pr-101",
    "title": "Harden admin middleware",
    "body": "Updates require_admin and related auth checks in src/auth.py.",
    "author": "alice",
    "labels": ["auth", "security"],
    "merged_at": "2026-03-20T00:00:00Z",
    "related_paths": ["src/auth.py", "require_admin"]
  },
  {
    "source_type": "issue",
    "external_ref": "issue-77",
    "title": "Admin route fails for privileged users",
    "body": "Possible regression around require_admin.",
    "author": "carol",
    "labels": ["bug"],
    "related_paths": ["require_admin"]
  }
]
""".strip(),
        encoding="utf-8",
    )
    ChangeMetadataIngestService(db_session).ingest_json_fixture(
        tenant_id=tenant.id,
        repo_id=repo.id,
        fixture_path=changes_fixture,
        acl_scope={"visibility": "private"},
    )

    dataset_path = tmp_path / "eval_coverage.yaml"
    dataset_path.write_text(
        f"""
name: eval-coverage
description: covers repo, dependency docs, and related changes
cases:
  - id: locate_auth
    query: where is admin authorization logic
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/auth.py
    expected_top_source: repo_code:src/auth.py
    expected_authorities:
      - repo
    expected_freshness_contains:
      - repository content
  - id: dependency_fastapi_migration
    tool: get_dependency_notes
    query: what changed in fastapi 0.115 migration
    task_type: migration
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    package_name: fastapi
    version_range: 0.115.x
    topic: migration
    must_hit_sources:
      - vendor_doc:https://fastapi.tiangolo.com/release-notes/
      - dependency_manifest:requirements.txt
    expected_top_source: vendor_doc:https://fastapi.tiangolo.com/release-notes/
    expected_authorities:
      - official
    expected_freshness_contains:
      - whitelisted domain
    expected_why_selected_contains:
      - matches package fastapi
    must_rank_before:
      - higher: vendor_doc:https://fastapi.tiangolo.com/release-notes/
        lower: dependency_manifest:requirements.txt
  - id: stale_fastapi_migration_note_conflict
    tool: get_dependency_notes
    query: compare stale internal fastapi migration note with official guidance
    task_type: migration
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    package_name: fastapi
    version_range: 0.115.x
    topic: migration
    must_hit_sources:
      - vendor_doc:https://fastapi.tiangolo.com/release-notes/
      - repo_doc:docs/fastapi-upgrade-notes.md
    expected_top_source: vendor_doc:https://fastapi.tiangolo.com/release-notes/
    expected_authorities:
      - official
      - repo
    expected_freshness_contains:
      - whitelisted domain
      - internal repository note
    must_rank_before:
      - higher: vendor_doc:https://fastapi.tiangolo.com/release-notes/
        lower: repo_doc:docs/fastapi-upgrade-notes.md
  - id: related_auth_changes
    query: harden admin middleware require_admin src/auth.py
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - pr:pr:pr-101
    expected_authorities:
      - repo
    expected_why_selected_contains:
      - signal
  - id: explain_admin_routes
    query: explain require_admin for admin routes
    task_type: explain
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_doc:docs/auth.md
      - repo_code:src/auth.py
    expected_authorities:
      - repo
    expected_freshness_contains:
      - repository content
    expected_why_selected_contains:
      - signal
  - id: ambiguity_admin_route_source
    query: where should i look first for admin route authorization behavior
    task_type: explain
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_doc:docs/auth.md
      - repo_code:src/auth.py
    expected_authorities:
      - repo
    expected_freshness_contains:
      - repository content
    expected_why_selected_contains:
      - signal
    requires_clarification: true
  - id: impact_admin_guard_changes
    query: what is impacted by require_admin changes
    task_type: impact_analysis
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/auth.py
      - repo_doc:docs/auth.md
    expected_authorities:
      - repo
    expected_freshness_contains:
      - repository content
    expected_why_selected_contains:
      - signal
  - id: debug_recent_auth_regression
    query: possible regression around require_admin for privileged users
    task_type: debug
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - issue:issue:issue-77
    expected_authorities:
      - repo
    expected_why_selected_contains:
      - signal
  - id: internal_fastapi_upgrade_note_lookup
    tool: get_dependency_notes
    query: where is our internal fastapi upgrade note
    task_type: migration
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    package_name: fastapi
    version_range: 0.115.x
    topic: migration
    must_hit_sources:
      - repo_doc:docs/fastapi-upgrade-notes.md
    expected_authorities:
      - official
      - repo
    expected_freshness_contains:
      - internal repository note
""".strip(),
        encoding="utf-8",
    )

    summary = EvalRunnerService(db_session).run_from_yaml(dataset_path)
    eval_case_rows = list(db_session.scalars(select(EvalCase)).all())
    eval_cases = {case.id: case.name for case in eval_case_rows}
    case_results = {
        eval_cases[result.eval_case_id]: result
        for result in db_session.scalars(select(EvalCaseResult)).all()
    }
    eval_cases_by_name = {case.name: case for case in eval_case_rows}

    assert summary["case_count"] == 9
    assert summary["recall_at_5"] == 1.0
    assert summary["evidence_contract_score"] == 1.0
    assert summary["overall_score"] >= 0.95
    assert (
        case_results["dependency_fastapi_migration"].result_payload["scores"][
            "rank_order_ok"
        ]
        == 1.0
    )
    assert (
        case_results["dependency_fastapi_migration"].result_payload["scores"][
            "top_source_ok"
        ]
        == 1.0
    )
    assert (
        case_results["dependency_fastapi_migration"].result_payload["scores"][
            "authority_match"
        ]
        == 1.0
    )
    assert (
        case_results["stale_fastapi_migration_note_conflict"].result_payload[
            "scores"
        ]["rank_order_ok"]
        == 1.0
    )
    assert (
        case_results["stale_fastapi_migration_note_conflict"].result_payload[
            "scores"
        ]["top_source_ok"]
        == 1.0
    )
    assert (
        case_results["locate_auth"].result_payload["scores"]["top_source_ok"]
        == 1.0
    )
    assert (
        case_results["explain_admin_routes"].result_payload["scores"]["authority_match"]
        == 1.0
    )
    assert (
        eval_cases_by_name["ambiguity_admin_route_source"].metadata_json[
            "requires_clarification"
        ]
        is True
    )
    assert (
        case_results["ambiguity_admin_route_source"].result_payload["scores"][
            "authority_match"
        ]
        == 1.0
    )
    assert (
        case_results["related_auth_changes"].result_payload["scores"]["retrieval_score"]
        >= 0.75
    )
    assert (
        case_results["impact_admin_guard_changes"].result_payload["scores"][
            "retrieval_score"
        ]
        == 1.0
    )
    assert (
        case_results["debug_recent_auth_regression"].result_payload["scores"][
            "retrieval_score"
        ]
        == 1.0
    )
    assert (
        case_results["internal_fastapi_upgrade_note_lookup"].result_payload["scores"][
            "authority_match"
        ]
        == 1.0
    )


def test_eval_runner_covers_debug_case_family(
    db_session,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "sample_repo_eval_debug"
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

    tenant = Tenant(name="Tenant Eval Debug", slug="tenant-eval-debug")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo-eval-debug",
        provider="local",
        external_id="sample-repo-eval-debug",
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

    dataset_path = tmp_path / "eval_debug_family.yaml"
    dataset_path.write_text(
        f"""
name: debug-family-eval
description: covers debug-style query behavior
cases:
  - id: debug_admin_permission_error
    query: admin only permission error in require_admin
    task_type: debug
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/auth.py
    expected_top_source: repo_code:src/auth.py
    expected_authorities:
      - repo
    expected_freshness_contains:
      - repository content
    expected_why_selected_contains:
      - signal
""".strip(),
        encoding="utf-8",
    )

    summary = EvalRunnerService(db_session).run_from_yaml(dataset_path)
    case_result = db_session.scalar(select(EvalCaseResult))

    assert summary["case_count"] == 1
    assert summary["overall_score"] >= 0.95
    assert case_result is not None
    assert case_result.result_payload["scores"]["top_source_ok"] == 1.0
    assert case_result.result_payload["scores"]["authority_match"] == 1.0


def test_eval_runner_tracks_acl_isolation_leakage_count(
    db_session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    tenant = Tenant(name="Tenant Eval ACL", slug="tenant-eval-acl")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo-eval-acl",
        provider="local",
        external_id="sample-repo-eval-acl",
        default_branch="main",
        acl_scope={"visibility": "private"},
    )
    db_session.add(repo)
    db_session.commit()

    runner = EvalRunnerService(db_session)
    monkeypatch.setattr(
        runner.tool_service,
        "search_context",
        lambda tenant_id, repo_id, query, task_type, top_k: {
            "evidence": [
                {
                    "source_type": "repo_code",
                    "path_or_url": "src/auth.py",
                    "authority": "repo",
                    "freshness_reason": (
                        "Freshness: repository content from latest local ingest snapshot"
                    ),
                    "why_selected": "Signal: lexical match",
                },
                {
                    "source_type": "repo_code",
                    "path_or_url": "src/secret_admin.py",
                    "authority": "repo",
                    "freshness_reason": (
                        "Freshness: repository content from latest local ingest snapshot"
                    ),
                    "why_selected": "Signal: lexical match",
                },
            ],
        },
    )

    dataset_path = tmp_path / "eval_acl_isolation.yaml"
    dataset_path.write_text(
        f"""
name: acl-isolation-eval
description: validates must-not-hit leakage tracking
cases:
  - id: acl_isolation_case
    query: where is admin authorization logic
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/auth.py
    must_not_hit_sources:
      - repo_code:src/secret_admin.py
""".strip(),
        encoding="utf-8",
    )

    summary = runner.run_from_yaml(dataset_path)
    case_result = db_session.scalar(select(EvalCaseResult))

    assert summary["failed_case_count"] == 1
    assert case_result is not None
    assert case_result.leakage_count == 1
    assert case_result.result_payload["scores"]["recall_at_5"] == 0.0
    assert case_result.result_payload["diagnostics"]["failed_checks"][0]["check"] == (
        "must_not_hit_sources"
    )


def test_eval_runner_scores_expected_top_source_constraint(
    db_session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    tenant = Tenant(name="Tenant Eval Top Source", slug="tenant-eval-top-source")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo-top-source",
        provider="local",
        external_id="sample-repo-top-source",
        default_branch="main",
        acl_scope={"visibility": "private"},
    )
    db_session.add(repo)
    db_session.commit()

    freshness_reason = (
        "Freshness: repository content from latest local ingest snapshot"
    )
    evidence_by_query = {
        "top source ok query": [
            {
                "source_type": "repo_code",
                "path_or_url": "src/auth.py",
                "authority": "repo",
                "freshness_reason": freshness_reason,
                "why_selected": "Signal: lexical match",
            },
            {
                "source_type": "repo_doc",
                "path_or_url": "docs/auth.md",
                "authority": "repo",
                "freshness_reason": freshness_reason,
                "why_selected": "Signal: lexical match",
            },
        ],
        "top source bad query": [
            {
                "source_type": "repo_doc",
                "path_or_url": "docs/auth.md",
                "authority": "repo",
                "freshness_reason": freshness_reason,
                "why_selected": "Signal: lexical match",
            },
            {
                "source_type": "repo_code",
                "path_or_url": "src/auth.py",
                "authority": "repo",
                "freshness_reason": freshness_reason,
                "why_selected": "Signal: lexical match",
            },
        ],
    }

    runner = EvalRunnerService(db_session)
    monkeypatch.setattr(
        runner.tool_service,
        "search_context",
        lambda tenant_id, repo_id, query, task_type, top_k: {
            "evidence": evidence_by_query[query],
        },
    )

    dataset_path = tmp_path / "eval_top_source.yaml"
    dataset_path.write_text(
        f"""
name: top-source-eval
description: eval strict top-source contract
cases:
  - id: top_source_ok
    query: top source ok query
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/auth.py
    expected_top_source: repo_code:src/auth.py
  - id: top_source_bad
    query: top source bad query
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/auth.py
    expected_top_source: repo_code:src/auth.py
""".strip(),
        encoding="utf-8",
    )

    summary = runner.run_from_yaml(dataset_path)
    eval_cases = {
        case.id: case.name for case in db_session.scalars(select(EvalCase)).all()
    }
    case_results = {
        eval_cases[result.eval_case_id]: result
        for result in db_session.scalars(select(EvalCaseResult)).all()
    }

    assert case_results["top_source_ok"].result_payload["scores"]["top_source_ok"] == 1.0
    assert case_results["top_source_bad"].result_payload["scores"]["top_source_ok"] == 0.0
    assert (
        case_results["top_source_ok"].result_payload["scores"]["evidence_contract_score"]
        == 1.0
    )
    assert (
        case_results["top_source_bad"].result_payload["scores"]["evidence_contract_score"]
        < 1.0
    )
    assert summary["evidence_contract_score"] < 1.0


def test_eval_runner_emits_per_case_diagnostics_for_failures(
    db_session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    tenant = Tenant(name="Tenant Eval Diagnostics", slug="tenant-eval-diagnostics")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo-diagnostics",
        provider="local",
        external_id="sample-repo-diagnostics",
        default_branch="main",
        acl_scope={"visibility": "private"},
    )
    db_session.add(repo)
    db_session.commit()

    freshness_reason = (
        "Freshness: repository content from latest local ingest snapshot"
    )
    runner = EvalRunnerService(db_session)
    monkeypatch.setattr(
        runner.tool_service,
        "search_context",
        lambda tenant_id, repo_id, query, task_type, top_k: {
            "evidence": [
                {
                    "source_type": "repo_doc",
                    "path_or_url": "docs/auth.md",
                    "authority": "repo",
                    "freshness_reason": freshness_reason,
                    "why_selected": "Signal: lexical match",
                },
                {
                    "source_type": "repo_code",
                    "path_or_url": "src/auth.py",
                    "authority": "repo",
                    "freshness_reason": freshness_reason,
                    "why_selected": "Signal: lexical match",
                },
            ],
        },
    )

    dataset_path = tmp_path / "eval_diagnostics.yaml"
    dataset_path.write_text(
        f"""
name: diagnostics-eval
description: eval diagnostics on failing case
cases:
  - id: diagnostics_case
    query: diagnostics query
    task_type: locate
    tenant_id: "{tenant.id}"
    repo_id: "{repo.id}"
    must_hit_sources:
      - repo_code:src/missing.py
    must_rank_before:
      - higher: repo_code:src/auth.py
        lower: repo_doc:docs/auth.md
    expected_top_source: repo_code:src/auth.py
""".strip(),
        encoding="utf-8",
    )

    summary = runner.run_from_yaml(dataset_path)
    case_result = db_session.scalar(select(EvalCaseResult))

    assert case_result is not None
    diagnostics = case_result.result_payload["diagnostics"]
    failed_checks = {item["check"]: item for item in diagnostics["failed_checks"]}

    assert failed_checks["must_hit_sources"]["expected"] == ["repo_code:src/missing.py"]
    assert failed_checks["must_hit_sources"]["actual"] == [
        "repo_doc:docs/auth.md",
        "repo_code:src/auth.py",
    ]
    assert failed_checks["rank_order_ok"]["expected"] == [
        {"higher": "repo_code:src/auth.py", "lower": "repo_doc:docs/auth.md"}
    ]
    assert failed_checks["top_source_ok"]["expected"] == "repo_code:src/auth.py"
    assert failed_checks["top_source_ok"]["actual"] == "repo_doc:docs/auth.md"
    assert diagnostics["actual"]["source_keys"] == [
        "repo_doc:docs/auth.md",
        "repo_code:src/auth.py",
    ]
    assert summary["failed_case_count"] == 1
    assert summary["failing_checks"] == {
        "must_hit_sources": 1,
        "rank_order_ok": 1,
        "top_source_ok": 1,
    }
