from pathlib import Path

from sqlalchemy import select

from repo_dependency_context_mcp.db.models import EvalCase, EvalCaseResult, EvalRun, Repo, Tenant
from repo_dependency_context_mcp.services.dependencies.parser import DependencyParserService
from repo_dependency_context_mcp.services.dependencies.vendor_docs import (
    VendorDocCandidate,
    VendorDocIngestService,
)
from repo_dependency_context_mcp.services.eval.runner import EvalRunnerService
from repo_dependency_context_mcp.services.ingest.change_metadata import ChangeMetadataIngestService
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
    assert summary["evidence_contract_score"] == 0.9


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
    expected_authorities:
      - official
    expected_freshness_contains:
      - whitelisted domain
    expected_why_selected_contains:
      - matches package fastapi
    must_rank_before:
      - higher: vendor_doc:https://fastapi.tiangolo.com/release-notes/
        lower: dependency_manifest:requirements.txt
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
""".strip(),
        encoding="utf-8",
    )

    summary = EvalRunnerService(db_session).run_from_yaml(dataset_path)
    eval_cases = {
        case.id: case.name for case in db_session.scalars(select(EvalCase)).all()
    }
    case_results = {
        eval_cases[result.eval_case_id]: result
        for result in db_session.scalars(select(EvalCaseResult)).all()
    }

    assert summary["case_count"] == 3
    assert summary["overall_score"] == 1.0
    assert (
        case_results["dependency_fastapi_migration"].result_payload["scores"][
            "rank_order_ok"
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
        case_results["related_auth_changes"].result_payload["scores"]["retrieval_score"]
        == 1.0
    )
