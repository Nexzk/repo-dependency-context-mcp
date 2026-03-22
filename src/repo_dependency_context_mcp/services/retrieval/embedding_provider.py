from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from openai import OpenAI

from repo_dependency_context_mcp.config import Settings


class EmbeddingProvider:
    def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError


@dataclass(slots=True)
class LocalEmbeddingProvider(EmbeddingProvider):
    dimension: int

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = [token for token in text.lower().split() if token]
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            index = int(digest[:8], 16) % self.dimension
            vector[index] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


@dataclass(slots=True)
class OpenAIEmbeddingProvider(EmbeddingProvider):
    api_key: str | None
    model: str

    def __post_init__(self) -> None:
        self.client = OpenAI(api_key=self.api_key)

    def embed_text(self, text: str) -> list[float]:
        response = self.client.embeddings.create(model=self.model, input=text)
        return list(response.data[0].embedding)


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    active_settings = settings or Settings()
    if active_settings.embedding_provider == "openai":
        return OpenAIEmbeddingProvider(
            api_key=active_settings.openai_api_key,
            model=active_settings.openai_embedding_model,
        )
    return LocalEmbeddingProvider(dimension=active_settings.embedding_dimension)
