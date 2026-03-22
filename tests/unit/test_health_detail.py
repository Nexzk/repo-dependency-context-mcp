from __future__ import annotations

from fastapi.testclient import TestClient

from repo_dependency_context_mcp.main import app


def test_healthz_includes_provider_configuration_status(monkeypatch) -> None:
    monkeypatch.setenv("RDCMCP_EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("RDCMCP_RERANK_PROVIDER", "local")

    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["providers"] == {
        "embedding_provider": "local",
        "rerank_provider": "local",
        "config_valid": True,
    }
