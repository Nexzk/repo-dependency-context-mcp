from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ChunkDraft:
    chunk_type: str
    text: str
    context_prefix: str
    token_count: int
    symbol_path: str | None = None
    metadata: dict = field(default_factory=dict)
