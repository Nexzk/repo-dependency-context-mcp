from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager

from mcp.server.fastmcp import FastMCP

from repo_dependency_context_mcp.schemas.mcp import (
    DependencyNotesResponse,
    GetSourceResponse,
    RelatedChangesResponse,
    SearchContextResponse,
)
from repo_dependency_context_mcp.services.mcp.tools import MCPToolService

SessionFactory = Callable[[], AbstractContextManager | object]


def build_mcp_server(session_factory: SessionFactory) -> FastMCP:
    server = FastMCP(
        name="Repo + Dependency Context MCP",
        instructions=(
            "Return minimal sufficient evidence packs for repository "
            "and dependency context."
        ),
    )

    @server.tool(
        name="search_context",
        description="Search repository and dependency context and return structured evidence.",
        structured_output=True,
    )
    def search_context(
        tenant_id: str,
        repo_id: str | None,
        query: str,
        task_type: str | None = None,
        top_k: int = 5,
    ) -> SearchContextResponse:
        with _session_scope(session_factory) as session:
            return SearchContextResponse.model_validate(MCPToolService(session).search_context(
                tenant_id=uuid.UUID(tenant_id),
                repo_id=uuid.UUID(repo_id) if repo_id else None,
                query=query,
                task_type=task_type,
                top_k=top_k,
            ))

    @server.tool(
        name="get_source",
        description="Get an exact source or document snippet by path and line range.",
        structured_output=True,
    )
    def get_source(
        tenant_id: str,
        repo_id: str,
        path_or_url: str,
        start_line: int,
        end_line: int,
    ) -> GetSourceResponse:
        with _session_scope(session_factory) as session:
            return GetSourceResponse.model_validate(MCPToolService(session).get_source(
                tenant_id=uuid.UUID(tenant_id),
                repo_id=uuid.UUID(repo_id),
                path_or_url=path_or_url,
                start_line=start_line,
                end_line=end_line,
            ))

    @server.tool(
        name="get_related_changes",
        description="Get related PR, commit, and issue summaries for a path or symbol.",
        structured_output=True,
    )
    def get_related_changes(
        tenant_id: str,
        repo_id: str,
        path_or_symbol: str,
        since_days: int = 90,
    ) -> RelatedChangesResponse:
        with _session_scope(session_factory) as session:
            return RelatedChangesResponse.model_validate(
                MCPToolService(session).get_related_changes(
                    tenant_id=uuid.UUID(tenant_id),
                    repo_id=uuid.UUID(repo_id),
                    path_or_symbol=path_or_symbol,
                    since_days=since_days,
                )
            )

    @server.tool(
        name="get_dependency_notes",
        description="Get official dependency docs, changelog, and migration snippets.",
        structured_output=True,
    )
    def get_dependency_notes(
        tenant_id: str,
        repo_id: str | None,
        package_name: str,
        version_range: str | None = None,
        topic: str | None = None,
        top_k: int = 5,
    ) -> DependencyNotesResponse:
        with _session_scope(session_factory) as session:
            return DependencyNotesResponse.model_validate(
                MCPToolService(session).get_dependency_notes(
                    tenant_id=uuid.UUID(tenant_id),
                    repo_id=uuid.UUID(repo_id) if repo_id else None,
                    package_name=package_name,
                    version_range=version_range,
                    topic=topic,
                    top_k=top_k,
                )
            )

    return server


class _session_scope:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._resource = None
        self._session = None

    def __enter__(self):
        self._resource = self._session_factory()
        if hasattr(self._resource, "__enter__"):
            self._session = self._resource.__enter__()
        else:
            self._session = self._resource
        return self._session

    def __exit__(self, exc_type, exc, tb) -> None:
        if hasattr(self._resource, "__exit__"):
            self._resource.__exit__(exc_type, exc, tb)
        elif hasattr(self._resource, "close"):
            self._resource.close()
