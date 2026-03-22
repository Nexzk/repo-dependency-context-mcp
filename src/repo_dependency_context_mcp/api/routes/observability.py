from __future__ import annotations

from collections import Counter

from fastapi import APIRouter
from sqlalchemy import desc, func, select

from repo_dependency_context_mcp.api.deps import get_db_session
from repo_dependency_context_mcp.db.models import (
    EvalCase,
    EvalCaseResult,
    EvalRun,
    IngestJob,
    QueryLog,
    SyncCursor,
    SyncRun,
)
from repo_dependency_context_mcp.services.ingest.sync_state import SyncStateService

router = APIRouter(prefix="/api/observability", tags=["observability"])


@router.get("/metrics")
def metrics() -> dict:
    with get_db_session() as session:
        sync_state = SyncStateService(session)
        latest_eval_runs = list_latest_eval_runs(session, limit=5)
        latest_eval_failures = list_latest_eval_failures(session)
        recent_eval_check_failures = aggregate_recent_eval_check_failures(latest_eval_runs)
        recent_eval_failed_cases = sum(
            int(run.summary_json.get("failed_case_count", 0))
            for run in latest_eval_runs
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
