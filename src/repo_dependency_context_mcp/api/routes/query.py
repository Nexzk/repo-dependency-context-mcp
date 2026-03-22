from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from repo_dependency_context_mcp.api.deps import get_db_session
from repo_dependency_context_mcp.services.mcp.tools import MCPToolService

router = APIRouter(prefix="/api", tags=["query"])


class SearchRequest(BaseModel):
    tenant_id: str
    repo_id: str | None = None
    query: str
    task_type: str | None = None
    top_k: int = 5


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
