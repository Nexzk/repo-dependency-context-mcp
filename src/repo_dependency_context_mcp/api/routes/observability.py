from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from repo_dependency_context_mcp.api.deps import get_db_session
from repo_dependency_context_mcp.db.models import EvalRun, IngestJob, QueryLog, SyncCursor, SyncRun
from repo_dependency_context_mcp.services.ingest.sync_state import SyncStateService

router = APIRouter(prefix="/api/observability", tags=["observability"])


@router.get("/metrics")
def metrics() -> dict:
    with get_db_session() as session:
        sync_state = SyncStateService(session)
        return {
            "ingest_jobs": session.scalar(select(func.count()).select_from(IngestJob)) or 0,
            "query_logs": session.scalar(select(func.count()).select_from(QueryLog)) or 0,
            "eval_runs": session.scalar(select(func.count()).select_from(EvalRun)) or 0,
            "sync_cursors": session.scalar(select(func.count()).select_from(SyncCursor)) or 0,
            "sync_runs": session.scalar(select(func.count()).select_from(SyncRun)) or 0,
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
