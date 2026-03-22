from __future__ import annotations

from fastapi import FastAPI

from repo_dependency_context_mcp.api.routes.eval import router as eval_router
from repo_dependency_context_mcp.api.routes.health import router as health_router
from repo_dependency_context_mcp.api.routes.observability import router as observability_router
from repo_dependency_context_mcp.api.routes.playground import router as playground_router
from repo_dependency_context_mcp.api.routes.query import router as query_router
from repo_dependency_context_mcp.config import Settings
from repo_dependency_context_mcp.logging import configure_logging

settings = Settings()
settings.validate()
configure_logging(settings)

app = FastAPI(title=settings.app_name)
app.include_router(health_router)
app.include_router(playground_router)
app.include_router(query_router)
app.include_router(eval_router)
app.include_router(observability_router)
