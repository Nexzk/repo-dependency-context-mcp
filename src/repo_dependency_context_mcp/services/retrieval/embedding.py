from __future__ import annotations

from repo_dependency_context_mcp.config import Settings
from repo_dependency_context_mcp.services.retrieval.embedding_provider import get_embedding_provider


def embed_text(text: str, settings: Settings | None = None) -> list[float]:
    return get_embedding_provider(settings).embed_text(text)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    return float(sum(a * b for a, b in zip(left, right, strict=False)))
