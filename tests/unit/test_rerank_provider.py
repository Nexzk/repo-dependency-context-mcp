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


def test_local_rerank_provider_prefers_repo_code_for_locate_queries() -> None:
    provider = LocalRerankProvider()

    ranked = provider.rerank(
        "where is require_admin defined in src/auth.py",
        [
            RerankItem(
                item_id="doc",
                text="Authentication docs require the require_admin helper.",
                base_score=0.8,
                metadata={
                    "task_type": "locate",
                    "source_type": "repo_doc",
                    "path_or_url": "docs/auth.md",
                    "symbol_path": "",
                    "authority": "repo",
                },
            ),
            RerankItem(
                item_id="code",
                text="def require_admin(user): return True",
                base_score=0.7,
                metadata={
                    "task_type": "locate",
                    "source_type": "repo_code",
                    "path_or_url": "src/auth.py",
                    "symbol_path": "require_admin",
                    "authority": "repo",
                },
            ),
        ],
    )

    assert ranked[0].item_id == "code"


def test_local_rerank_provider_prefers_vendor_docs_for_migration_queries() -> None:
    provider = LocalRerankProvider()

    ranked = provider.rerank(
        "what changed in fastapi migration",
        [
            RerankItem(
                item_id="manifest",
                text="fastapi==0.115.0 declared via pip",
                base_score=0.8,
                metadata={
                    "task_type": "migration",
                    "source_type": "dependency_manifest",
                    "path_or_url": "requirements.txt",
                    "symbol_path": "",
                    "authority": "repo",
                },
            ),
            RerankItem(
                item_id="vendor",
                text="FastAPI migration guide covering migration changes.",
                base_score=0.75,
                metadata={
                    "task_type": "migration",
                    "source_type": "vendor_doc",
                    "path_or_url": "https://fastapi.tiangolo.com/release-notes/",
                    "symbol_path": "",
                    "authority": "official",
                },
            ),
        ],
    )

    assert ranked[0].item_id == "vendor"


def test_authority_boost_rerank_profile_strengthens_vendor_doc_preference() -> None:
    default_provider = LocalRerankProvider(profile="local_task_aware_v2")
    boosted_provider = LocalRerankProvider(
        profile="local_task_aware_authority_boost_v1"
    )
    manifest = RerankItem(
        item_id="manifest",
        text="fastapi==0.115.0 declared via pip",
        base_score=0.95,
        metadata={
            "task_type": "migration",
            "source_type": "dependency_manifest",
            "path_or_url": "requirements.txt",
            "symbol_path": "",
            "authority": "repo",
        },
    )
    vendor = RerankItem(
        item_id="vendor",
        text="FastAPI migration guide covering migration changes.",
        base_score=0.7,
        metadata={
            "task_type": "migration",
            "source_type": "vendor_doc",
            "path_or_url": "https://fastapi.tiangolo.com/release-notes/",
            "symbol_path": "",
            "authority": "official",
        },
    )

    default_gap = default_provider._score_item(
        "what changed in fastapi migration",
        vendor,
    ) - default_provider._score_item(
        "what changed in fastapi migration",
        manifest,
    )
    boosted_gap = boosted_provider._score_item(
        "what changed in fastapi migration",
        vendor,
    ) - boosted_provider._score_item(
        "what changed in fastapi migration",
        manifest,
    )

    assert boosted_gap > default_gap


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
