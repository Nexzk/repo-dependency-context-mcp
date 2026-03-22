from __future__ import annotations

from repo_dependency_context_mcp.config import Settings
from repo_dependency_context_mcp.services.retrieval.rerank_provider import (
    LocalRerankProvider,
    OpenAIRerankProvider,
    RerankItem,
    get_rerank_provider,
)


def test_default_rerank_provider_is_local() -> None:
    settings = Settings()
    settings.rerank_provider = "local"

    provider = get_rerank_provider(settings)

    assert isinstance(provider, LocalRerankProvider)
    ranked = provider.rerank(
        "require_admin",
        [
            RerankItem(item_id="a", text="require_admin guard", base_score=0.1),
            RerankItem(item_id="b", text="unrelated billing", base_score=0.9),
        ],
    )
    assert ranked[0].item_id == "a"


def test_openai_rerank_provider_uses_chat_client(monkeypatch) -> None:
    class FakeResponses:
        def create(self, **kwargs):
            return type(
                "Response",
                (),
                {
                    "output_text": '[{"item_id":"b","score":0.9},{"item_id":"a","score":0.4}]'
                },
            )()

    class FakeClient:
        def __init__(self, api_key: str | None = None) -> None:
            assert api_key == "test-key"
            self.responses = FakeResponses()

    monkeypatch.setattr(
        "repo_dependency_context_mcp.services.retrieval.rerank_provider.OpenAI",
        FakeClient,
    )

    settings = Settings()
    settings.rerank_provider = "openai"
    settings.openai_api_key = "test-key"
    settings.openai_rerank_model = "gpt-5-mini"

    provider = get_rerank_provider(settings)

    assert isinstance(provider, OpenAIRerankProvider)
    ranked = provider.rerank(
        "require_admin",
        [
            RerankItem(item_id="a", text="require_admin guard", base_score=0.1),
            RerankItem(item_id="b", text="billing invoice", base_score=0.2),
        ],
    )
    assert ranked[0].item_id == "b"
