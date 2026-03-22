from __future__ import annotations

from repo_dependency_context_mcp.db.models import Chunk, Document, Source


def build_evidence_item(
    chunk: Chunk,
    document: Document,
    source: Source,
    why_selected: str,
    freshness_reason: str,
) -> dict:
    return {
        "source_type": source.source_type,
        "title": document.title,
        "path_or_url": source.path_or_url,
        "symbol_path": chunk.symbol_path,
        "start_line": chunk.metadata_json.get("start_line"),
        "end_line": chunk.metadata_json.get("end_line"),
        "snippet": chunk.text[:500],
        "why_selected": why_selected,
        "freshness_reason": freshness_reason,
        "authority": chunk.authority,
        "version_range": chunk.version_range,
    }
