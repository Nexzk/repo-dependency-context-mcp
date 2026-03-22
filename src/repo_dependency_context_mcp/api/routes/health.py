from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from repo_dependency_context_mcp.api.deps import get_settings

router = APIRouter()


class ProviderStatus(BaseModel):
    embedding_provider: str
    rerank_provider: str
    config_valid: bool


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
    providers: ProviderStatus


@router.get("/healthz", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    settings = get_settings()
    config_valid = True
    try:
        settings.validate()
    except ValueError:
        config_valid = False
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        environment=settings.env,
        providers=ProviderStatus(
            embedding_provider=settings.embedding_provider,
            rerank_provider=settings.rerank_provider,
            config_valid=config_valid,
        ),
    )
