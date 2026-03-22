from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from repo_dependency_context_mcp.api.deps import get_db_session
from repo_dependency_context_mcp.db.models import EvalRun, IngestJob, QueryLog

router = APIRouter(prefix="/api/observability", tags=["observability"])


@router.get("/metrics")
def metrics() -> dict:
    with get_db_session() as session:
        return {
            "ingest_jobs": session.scalar(select(func.count()).select_from(IngestJob)) or 0,
            "query_logs": session.scalar(select(func.count()).select_from(QueryLog)) or 0,
            "eval_runs": session.scalar(select(func.count()).select_from(EvalRun)) or 0,
        }
