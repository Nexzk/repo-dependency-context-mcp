from __future__ import annotations

import pytest

from repo_dependency_context_mcp.config import Settings


def test_openai_embedding_provider_requires_api_key() -> None:
    settings = Settings()
    settings.embedding_provider = "openai"
    settings.openai_api_key = None

    with pytest.raises(ValueError, match="openai api key"):
        settings.validate()


def test_openai_rerank_provider_requires_api_key() -> None:
    settings = Settings()
    settings.rerank_provider = "openai"
    settings.openai_api_key = None

    with pytest.raises(ValueError, match="openai api key"):
        settings.validate()
