from fastapi.testclient import TestClient

from repo_dependency_context_mcp.config import Settings
from repo_dependency_context_mcp.main import app


def test_healthz_returns_service_metadata() -> None:
    client = TestClient(app)
    settings = Settings()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "repo-dependency-context-mcp",
        "environment": settings.env,
        "providers": {
            "embedding_provider": settings.embedding_provider,
            "rerank_provider": settings.rerank_provider,
            "config_valid": True,
        },
    }
