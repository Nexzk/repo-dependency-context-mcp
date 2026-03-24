from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from repo_dependency_context_mcp.api.deps import get_db_session
from repo_dependency_context_mcp.db.models import QueryFeedback, QueryLog, QueryResult
from repo_dependency_context_mcp.services.eval.feedback_export import (
    FeedbackEvalExportService,
)
from repo_dependency_context_mcp.services.mcp.tools import MCPToolService

router = APIRouter(prefix="/api", tags=["query"])


class SearchRequest(BaseModel):
    tenant_id: str
    repo_id: str | None = None
    query: str
    task_type: str | None = None
    top_k: int = 5


class FeedbackRequest(BaseModel):
    query_log_id: str
    feedback_type: str
    query_result_id: str | None = None
    notes: str | None = None
    expected_source_keys: list[str] = []
    metadata: dict = {}


@router.post("/query/search")
def search_context(request: SearchRequest) -> dict:
    with get_db_session() as session:
        return MCPToolService(session).search_context(
            tenant_id=uuid.UUID(request.tenant_id),
            repo_id=uuid.UUID(request.repo_id) if request.repo_id else None,
            query=request.query,
            task_type=request.task_type,
            top_k=request.top_k,
        )


@router.post("/query/feedback")
def ingest_feedback(request: FeedbackRequest) -> dict:
    allowed_feedback_types = {
        "correct",
        "missed_document",
        "stale_document",
        "wrong_source",
        "acl_problem",
    }
    if request.feedback_type not in allowed_feedback_types:
        raise HTTPException(status_code=400, detail="Unsupported feedback_type")

    with get_db_session() as session:
        query_log = session.get(QueryLog, uuid.UUID(request.query_log_id))
        if query_log is None:
            raise HTTPException(status_code=404, detail="query_log not found")

        query_result_id = (
            uuid.UUID(request.query_result_id) if request.query_result_id else None
        )
        if query_result_id is not None:
            query_result = session.get(QueryResult, query_result_id)
            if query_result is None or query_result.query_log_id != query_log.id:
                raise HTTPException(
                    status_code=400,
                    detail="query_result_id does not belong to query_log_id",
                )

        feedback = QueryFeedback(
            tenant_id=query_log.tenant_id,
            repo_id=query_log.repo_id,
            query_log_id=query_log.id,
            query_result_id=query_result_id,
            feedback_type=request.feedback_type,
            notes=request.notes,
            expected_source_keys=request.expected_source_keys,
            metadata_json=request.metadata,
        )
        session.add(feedback)
        session.commit()

        return {
            "feedback_id": str(feedback.id),
            "query_log_id": str(query_log.id),
            "query_result_id": str(query_result_id) if query_result_id else None,
            "feedback_type": feedback.feedback_type,
            "expected_source_keys": feedback.expected_source_keys,
        }


@router.get("/query/feedback/export")
def export_feedback_as_eval_dataset(
    tenant_id: str,
    repo_id: str | None = None,
    limit: int = 50,
    feedback_type: str | None = None,
) -> dict:
    with get_db_session() as session:
        return FeedbackEvalExportService(session).export_dataset_payload(
            tenant_id=uuid.UUID(tenant_id),
            repo_id=uuid.UUID(repo_id) if repo_id else None,
            limit=limit,
            feedback_type=feedback_type,
        )
