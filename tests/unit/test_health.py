from fastapi.testclient import TestClient

from repo_dependency_context_mcp.main import app


def test_healthz_returns_service_metadata() -> None:
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "repo-dependency-context-mcp",
        "environment": "test",
        "providers": {
            "embedding_provider": "local",
            "rerank_provider": "local",
            "config_valid": True,
        },
    }
