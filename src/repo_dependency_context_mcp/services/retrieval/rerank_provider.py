from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from repo_dependency_context_mcp.config import Settings


@dataclass(slots=True)
class RerankItem:
    item_id: str
    text: str
    base_score: float
    metadata: dict[str, Any] | None = None


class RerankProvider:
    def rerank(self, query: str, items: list[RerankItem]) -> list[RerankItem]:
        raise NotImplementedError


class LocalRerankProvider(RerankProvider):
    def rerank(self, query: str, items: list[RerankItem]) -> list[RerankItem]:
        tokens = _tokenize(query)

        def score(item: RerankItem) -> float:
            metadata = item.metadata or {}
            item_text = item.text.lower()
            overlap = sum(1 for token in tokens if token in item_text)
            source_type = str(metadata.get("source_type", ""))
            path_or_url = str(metadata.get("path_or_url", "")).lower()
            symbol_path = str(metadata.get("symbol_path", "")).lower()
            authority = str(metadata.get("authority", "")).lower()
            task_type = str(metadata.get("task_type", "")).lower()

            score_total = item.base_score + (overlap * 1.0)

            # Reward exact path mentions to stabilize file-targeting queries.
            if path_or_url and path_or_url in query.lower():
                score_total += 3.0

            path_tokens = _tokenize(path_or_url)
            symbol_tokens = _tokenize(symbol_path)
            score_total += sum(0.6 for token in tokens if token in path_tokens)
            score_total += sum(0.8 for token in tokens if token in symbol_tokens)

            if authority == "official":
                score_total += 0.35
            elif authority == "repo":
                score_total += 0.2

            if task_type == "locate":
                if source_type == "repo_code":
                    score_total += 2.0
                elif source_type == "repo_doc":
                    score_total += 1.0
                elif source_type in {"pr", "commit", "issue"}:
                    score_total -= 0.25
            elif task_type == "migration":
                if source_type == "vendor_doc":
                    score_total += 2.0
                elif source_type == "dependency_manifest":
                    score_total += 1.0

            # Prefer direct source paths over longer less-specific items.
            if path_or_url:
                score_total += max(0.0, 0.3 - (len(path_or_url) * 0.002))

            return score_total

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
            "items": [
                {
                    "item_id": item.item_id,
                    "text": item.text,
                    "base_score": item.base_score,
                    "metadata": item.metadata or {},
                }
                for item in items
            ],
        }
        response = self.client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Return a JSON array of items sorted by relevance. "
                        "Each item must contain item_id and score."
                    ),
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


def _tokenize(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9_./-]+", value.lower())
        if token and len(token) >= 2
    }
