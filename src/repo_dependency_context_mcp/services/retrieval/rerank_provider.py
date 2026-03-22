from __future__ import annotations

import json
from dataclasses import dataclass

from openai import OpenAI

from repo_dependency_context_mcp.config import Settings


@dataclass(slots=True)
class RerankItem:
    item_id: str
    text: str
    base_score: float


class RerankProvider:
    def rerank(self, query: str, items: list[RerankItem]) -> list[RerankItem]:
        raise NotImplementedError


class LocalRerankProvider(RerankProvider):
    def rerank(self, query: str, items: list[RerankItem]) -> list[RerankItem]:
        tokens = set(query.lower().split())

        def score(item: RerankItem) -> float:
            overlap = sum(1 for token in tokens if token in item.text.lower())
            return (overlap * 1.0) + item.base_score

        return sorted(items, key=score, reverse=True)


@dataclass(slots=True)
class OpenAIRerankProvider(RerankProvider):
    api_key: str | None
    model: str

    def __post_init__(self) -> None:
        self.client = OpenAI(api_key=self.api_key)

    def rerank(self, query: str, items: list[RerankItem]) -> list[RerankItem]:
        prompt = {
            "query": query,
            "items": [{"item_id": item.item_id, "text": item.text, "base_score": item.base_score} for item in items],
        }
        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": "Return a JSON array of items sorted by relevance. Each item must contain item_id and score.",
                },
                {
                    "role": "user",
                    "content": json.dumps(prompt),
                },
            ],
        )
        ranking = json.loads(response.output_text)
        by_id = {item.item_id: item for item in items}
        ordered: list[RerankItem] = []
        for row in ranking:
            item = by_id.get(row["item_id"])
            if item is not None:
                ordered.append(item)
        return ordered or items


def get_rerank_provider(settings: Settings | None = None) -> RerankProvider:
    active_settings = settings or Settings()
    if active_settings.rerank_provider == "openai":
        return OpenAIRerankProvider(
            api_key=active_settings.openai_api_key,
            model=active_settings.openai_rerank_model,
        )
    return LocalRerankProvider()
