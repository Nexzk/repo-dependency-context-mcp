from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select

from repo_dependency_context_mcp.db.models import QueryFeedback, QueryLog, QueryResult

JSONDict = dict[str, Any]


class FeedbackEvalExportService:
    def __init__(self, session) -> None:
        self.session = session

    def export_dataset_payload(
        self,
        *,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID | None = None,
        limit: int = 50,
        feedback_type: str | None = None,
    ) -> dict:
        rows = self._list_feedback_rows(
            tenant_id=tenant_id,
            repo_id=repo_id,
            limit=limit,
            feedback_type=feedback_type,
        )
        cases = [
            self._build_case(feedback, query_log, query_result)
            for feedback, query_log, query_result in rows
        ]
        suffix = datetime.now(UTC).strftime("%Y%m%d")
        return {
            "name": f"feedback-incremental-{suffix}",
            "description": "Incremental eval cases exported from online feedback",
            "metadata": {
                "feedback_count": len(cases),
                "feedback_type": feedback_type,
                "tenant_id": str(tenant_id),
                "repo_id": str(repo_id) if repo_id else None,
            },
            "cases": cases,
        }

    def _list_feedback_rows(
        self,
        *,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        limit: int,
        feedback_type: str | None,
    ) -> list[tuple[QueryFeedback, QueryLog, QueryResult | None]]:
        stmt = (
            select(QueryFeedback, QueryLog, QueryResult)
            .join(QueryLog, QueryLog.id == QueryFeedback.query_log_id)
            .outerjoin(QueryResult, QueryResult.id == QueryFeedback.query_result_id)
            .where(QueryFeedback.tenant_id == tenant_id)
            .order_by(desc(QueryFeedback.created_at))
            .limit(limit)
        )
        if repo_id is not None:
            stmt = stmt.where(QueryFeedback.repo_id == repo_id)
        if feedback_type:
            stmt = stmt.where(QueryFeedback.feedback_type == feedback_type)
        return self.session.execute(stmt).all()

    def _build_case(
        self,
        feedback: QueryFeedback,
        query_log: QueryLog,
        query_result: QueryResult | None,
    ) -> JSONDict:
        expected_source_keys = [str(value) for value in feedback.expected_source_keys]
        offending_source = self._offending_source_key(query_result)

        must_hit_sources = list(expected_source_keys)
        must_not_hit_sources: list[str] = []
        if feedback.feedback_type in {"wrong_source", "stale_document", "acl_problem"}:
            if offending_source:
                must_not_hit_sources.append(offending_source)
        if feedback.feedback_type == "correct" and not must_hit_sources and offending_source:
            must_hit_sources.append(offending_source)

        case: JSONDict = {
            "id": f"feedback_{feedback.feedback_type}_{str(feedback.id)[:8]}",
            "query": query_log.query_text,
            "task_type": query_log.task_type,
            "tenant_id": str(query_log.tenant_id),
            "repo_id": str(query_log.repo_id) if query_log.repo_id else None,
            "must_hit_sources": must_hit_sources,
            "must_not_hit_sources": must_not_hit_sources,
            "requires_clarification": query_log.clarify_needed,
            "metadata": {
                "feedback_id": str(feedback.id),
                "query_log_id": str(query_log.id),
                "query_result_id": (
                    str(feedback.query_result_id)
                    if feedback.query_result_id
                    else None
                ),
                "feedback_type": feedback.feedback_type,
                "feedback_notes": feedback.notes,
            },
        }
        if must_hit_sources:
            case["expected_top_source"] = must_hit_sources[0]
        return case

    @staticmethod
    def _offending_source_key(query_result: QueryResult | None) -> str | None:
        if query_result is None:
            return None
        evidence = query_result.evidence_payload or {}
        source_type = evidence.get("source_type")
        path_or_url = evidence.get("path_or_url")
        if not source_type or not path_or_url:
            return None
        return f"{source_type}:{path_or_url}"
