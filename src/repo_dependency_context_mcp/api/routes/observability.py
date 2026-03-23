from __future__ import annotations

from collections import Counter

from fastapi import APIRouter
from sqlalchemy import desc, func, select

from repo_dependency_context_mcp.api.deps import get_db_session
from repo_dependency_context_mcp.db.models import (
    EvalCase,
    EvalCaseResult,
    EvalDataset,
    EvalRun,
    IngestJob,
    QueryLog,
    SyncCursor,
    SyncRun,
)
from repo_dependency_context_mcp.services.ingest.sync_state import SyncStateService

router = APIRouter(prefix="/api/observability", tags=["observability"])


@router.get("/metrics")
def metrics(baseline_dataset_name: str | None = None) -> dict:
    with get_db_session() as session:
        sync_state = SyncStateService(session)
        latest_eval_runs = list_latest_eval_runs(session, limit=5)
        latest_eval_failures = list_latest_eval_failures(session)
        recent_eval_check_failures = aggregate_recent_eval_check_failures(latest_eval_runs)
        recent_eval_failed_cases = sum(
            int(run.summary_json.get("failed_case_count", 0))
            for run in latest_eval_runs
        )
        recent_eval_score_trend = build_recent_eval_score_trend(latest_eval_runs)
        recent_eval_score_summary = summarize_recent_eval_scores(latest_eval_runs)
        latest_eval_comparison = build_latest_eval_comparison(latest_eval_runs)
        latest_eval_matrix_summary = build_latest_eval_matrix_summary(
            list_latest_eval_runs(session, limit=20)
        )
        selected_eval_comparison = build_selected_eval_comparison(
            session=session,
            latest_runs=latest_eval_runs,
            baseline_dataset_name=baseline_dataset_name,
        )
        return {
            "ingest_jobs": session.scalar(select(func.count()).select_from(IngestJob)) or 0,
            "query_logs": session.scalar(select(func.count()).select_from(QueryLog)) or 0,
            "eval_runs": session.scalar(select(func.count()).select_from(EvalRun)) or 0,
            "sync_cursors": session.scalar(select(func.count()).select_from(SyncCursor)) or 0,
            "sync_runs": session.scalar(select(func.count()).select_from(SyncRun)) or 0,
            "latest_eval_runs": [
                _serialize_eval_run(run)
                for run in latest_eval_runs
            ],
            "latest_eval_failures": latest_eval_failures,
            "recent_eval_check_failures": recent_eval_check_failures,
            "recent_eval_failed_cases": recent_eval_failed_cases,
            "recent_eval_window": len(latest_eval_runs),
            "recent_eval_score_trend": recent_eval_score_trend,
            "recent_eval_score_summary": recent_eval_score_summary,
            "latest_eval_comparison": latest_eval_comparison,
            "latest_eval_matrix_summary": latest_eval_matrix_summary,
            "selected_eval_comparison": selected_eval_comparison,
            "latest_sync_runs": [
                {
                    "source_kind": run.source_kind,
                    "scope_key": run.scope_key,
                    "status": run.status,
                    "items_seen": run.items_seen,
                    "items_written": run.items_written,
                }
                for run in sync_state.list_latest_runs(limit=5)
            ],
            "latest_sync_cursors": [
                {
                    "source_kind": cursor.source_kind,
                    "scope_key": cursor.scope_key,
                    "cursor_value": cursor.cursor_value,
                }
                for cursor in sync_state.list_cursors(limit=5)
            ],
        }


def list_latest_eval_runs(session, limit: int = 5) -> list[EvalRun]:
    return session.scalars(
        select(EvalRun).order_by(desc(EvalRun.created_at)).limit(limit)
    ).all()


def _serialize_eval_run(run: EvalRun) -> dict:
    return {
        "dataset_id": str(run.dataset_id),
        "status": run.status,
        "overall_score": run.summary_json.get("overall_score"),
        "failed_case_count": run.summary_json.get("failed_case_count", 0),
        "failing_checks": run.summary_json.get("failing_checks", {}),
        "retrieval_profiles": run.summary_json.get("retrieval_profiles", {}),
    }


def list_latest_eval_failures(session) -> list[dict]:
    latest_run = session.scalar(select(EvalRun).order_by(desc(EvalRun.created_at)).limit(1))
    if latest_run is None:
        return []

    rows = session.execute(
        select(EvalCaseResult, EvalCase)
        .join(EvalCase, EvalCase.id == EvalCaseResult.eval_case_id)
        .where(EvalCaseResult.eval_run_id == latest_run.id)
        .order_by(EvalCase.created_at)
    ).all()

    failures: list[dict] = []
    for case_result, eval_case in rows:
        diagnostics = case_result.result_payload.get("diagnostics", {})
        failed_checks = diagnostics.get("failed_checks", [])
        if not failed_checks:
            continue
        failures.append(
            {
                "case_name": eval_case.name,
                "query_text": eval_case.query_text,
                "failed_checks": failed_checks,
                "top_evidence_sources": diagnostics.get("actual", {}).get("source_keys", [])[:3],
            }
        )
    return failures


def aggregate_recent_eval_check_failures(runs: list[EvalRun]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for run in runs:
        counter.update(
            {
                str(check): int(count)
                for check, count in run.summary_json.get("failing_checks", {}).items()
            }
        )
    return dict(counter)


def build_recent_eval_score_trend(runs: list[EvalRun]) -> list[dict]:
    return [
        {
            "dataset_id": str(run.dataset_id),
            "overall_score": float(run.summary_json.get("overall_score", 0.0)),
            "retrieval_score": float(run.summary_json.get("retrieval_score", 0.0)),
            "evidence_contract_score": float(
                run.summary_json.get("evidence_contract_score", 0.0)
            ),
            "failed_case_count": int(run.summary_json.get("failed_case_count", 0)),
            "retrieval_profiles": run.summary_json.get("retrieval_profiles", {}),
        }
        for run in runs
    ]


def summarize_recent_eval_scores(runs: list[EvalRun]) -> dict:
    if not runs:
        return {
            "window": 0,
            "avg_overall_score": 0.0,
            "avg_retrieval_score": 0.0,
            "avg_evidence_contract_score": 0.0,
        }

    overall_scores = [float(run.summary_json.get("overall_score", 0.0)) for run in runs]
    retrieval_scores = [float(run.summary_json.get("retrieval_score", 0.0)) for run in runs]
    evidence_scores = [
        float(run.summary_json.get("evidence_contract_score", 0.0))
        for run in runs
    ]
    count = len(runs)
    return {
        "window": count,
        "avg_overall_score": sum(overall_scores) / count,
        "avg_retrieval_score": sum(retrieval_scores) / count,
        "avg_evidence_contract_score": sum(evidence_scores) / count,
    }


def build_latest_eval_comparison(runs: list[EvalRun]) -> dict | None:
    if len(runs) < 2:
        return None

    return build_eval_comparison(current=runs[0], baseline=runs[1], baseline_source="latest")


def build_latest_eval_matrix_summary(runs: list[EvalRun]) -> dict | None:
    latest_batch_id: str | None = None
    for run in runs:
        matrix = run.summary_json.get("matrix", {})
        batch_id = matrix.get("batch_id")
        if isinstance(batch_id, str) and batch_id:
            latest_batch_id = batch_id
            break

    if latest_batch_id is None:
        return None

    matrix_runs = [
        run
        for run in runs
        if run.summary_json.get("matrix", {}).get("batch_id") == latest_batch_id
    ]
    if not matrix_runs:
        return None

    best_run = max(
        matrix_runs,
        key=lambda run: (
            float(run.summary_json.get("overall_score", 0.0)),
            float(run.summary_json.get("retrieval_score", 0.0)),
            -int(run.summary_json.get("failed_case_count", 0)),
        ),
    )
    first_matrix = matrix_runs[0].summary_json.get("matrix", {})
    return {
        "batch_id": latest_batch_id,
        "run_count": len(matrix_runs),
        "base_dataset_name": first_matrix.get("base_dataset_name"),
        "best_run": {
            "dataset_id": str(best_run.dataset_id),
            "candidate_profile": best_run.summary_json.get("retrieval_profiles", {}).get(
                "candidate_profile"
            ),
            "rerank_profile": best_run.summary_json.get("retrieval_profiles", {}).get(
                "rerank_profile"
            ),
            "overall_score": float(best_run.summary_json.get("overall_score", 0.0)),
            "retrieval_score": float(best_run.summary_json.get("retrieval_score", 0.0)),
            "evidence_contract_score": float(
                best_run.summary_json.get("evidence_contract_score", 0.0)
            ),
            "failed_case_count": int(best_run.summary_json.get("failed_case_count", 0)),
        },
        "runs": [
            {
                "dataset_id": str(run.dataset_id),
                "candidate_profile": run.summary_json.get("retrieval_profiles", {}).get(
                    "candidate_profile"
                ),
                "rerank_profile": run.summary_json.get("retrieval_profiles", {}).get(
                    "rerank_profile"
                ),
                "overall_score": float(run.summary_json.get("overall_score", 0.0)),
                "failed_case_count": int(run.summary_json.get("failed_case_count", 0)),
            }
            for run in matrix_runs
        ],
    }


def build_selected_eval_comparison(
    session,
    latest_runs: list[EvalRun],
    baseline_dataset_name: str | None,
) -> dict | None:
    if not latest_runs:
        return None
    if not baseline_dataset_name:
        return build_latest_eval_comparison(latest_runs)

    baseline_run = session.scalar(
        select(EvalRun)
        .join(EvalDataset, EvalDataset.id == EvalRun.dataset_id)
        .where(EvalDataset.name == baseline_dataset_name)
        .order_by(desc(EvalRun.created_at))
        .limit(1)
    )
    if baseline_run is None:
        return None

    current = latest_runs[0]
    return build_eval_comparison(
        current=current,
        baseline=baseline_run,
        baseline_source=baseline_dataset_name,
    )


def build_eval_comparison(
    current: EvalRun,
    baseline: EvalRun,
    baseline_source: str,
) -> dict:
    current_summary = current.summary_json
    baseline_summary = baseline.summary_json

    return {
        "baseline_source": baseline_source,
        "current_dataset_id": str(current.dataset_id),
        "previous_dataset_id": str(baseline.dataset_id),
        "current_overall_score": float(current_summary.get("overall_score", 0.0)),
        "previous_overall_score": float(baseline_summary.get("overall_score", 0.0)),
        "delta_overall_score": float(current_summary.get("overall_score", 0.0))
        - float(baseline_summary.get("overall_score", 0.0)),
        "current_retrieval_score": float(current_summary.get("retrieval_score", 0.0)),
        "previous_retrieval_score": float(baseline_summary.get("retrieval_score", 0.0)),
        "delta_retrieval_score": float(current_summary.get("retrieval_score", 0.0))
        - float(baseline_summary.get("retrieval_score", 0.0)),
        "current_evidence_contract_score": float(
            current_summary.get("evidence_contract_score", 0.0)
        ),
        "previous_evidence_contract_score": float(
            baseline_summary.get("evidence_contract_score", 0.0)
        ),
        "delta_evidence_contract_score": float(
            current_summary.get("evidence_contract_score", 0.0)
        )
        - float(baseline_summary.get("evidence_contract_score", 0.0)),
        "current_failed_case_count": int(current_summary.get("failed_case_count", 0)),
        "previous_failed_case_count": int(baseline_summary.get("failed_case_count", 0)),
        "delta_failed_case_count": int(current_summary.get("failed_case_count", 0))
        - int(baseline_summary.get("failed_case_count", 0)),
        "current_failing_checks": current_summary.get("failing_checks", {}),
        "previous_failing_checks": baseline_summary.get("failing_checks", {}),
        "current_retrieval_profiles": current_summary.get("retrieval_profiles", {}),
        "previous_retrieval_profiles": baseline_summary.get("retrieval_profiles", {}),
    }
