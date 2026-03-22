from __future__ import annotations

from repo_dependency_context_mcp.config import Settings
from repo_dependency_context_mcp.services.retrieval.embedding_provider import (
    LocalEmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_provider,
)


def test_default_embedding_provider_is_local() -> None:
    settings = Settings()
    settings.embedding_provider = "local"

    provider = get_embedding_provider(settings)

    assert isinstance(provider, LocalEmbeddingProvider)
    vector = provider.embed_text("require admin access")
    assert len(vector) == settings.embedding_dimension


def test_openai_embedding_provider_uses_client(monkeypatch) -> None:
    class FakeEmbeddings:
        def create(self, *, model, input):  # noqa: A002
            assert model == "text-embedding-3-small"
            assert input == "auth middleware"
            return type(
                "Response",
                (),
                {"data": [type("Item", (), {"embedding": [0.1, 0.2, 0.3]})()]},
            )()

    class FakeClient:
        def __init__(self, api_key: str | None = None) -> None:
            assert api_key == "test-key"
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr(
        "repo_dependency_context_mcp.services.retrieval.embedding_provider.OpenAI",
        FakeClient,
    )

    settings = Settings()
    settings.embedding_provider = "openai"
    settings.openai_api_key = "test-key"
    settings.openai_embedding_model = "text-embedding-3-small"

    provider = get_embedding_provider(settings)

    assert isinstance(provider, OpenAIEmbeddingProvider)
    assert provider.embed_text("auth middleware") == [0.1, 0.2, 0.3]
