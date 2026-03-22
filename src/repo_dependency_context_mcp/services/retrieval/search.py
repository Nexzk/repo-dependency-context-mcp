from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC

from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session

from repo_dependency_context_mcp.config import Settings
from repo_dependency_context_mcp.db.models import Chunk, Document, QueryLog, QueryResult, Source
from repo_dependency_context_mcp.services.packing.evidence import build_evidence_item
from repo_dependency_context_mcp.services.retrieval.embedding import cosine_similarity, embed_text
from repo_dependency_context_mcp.services.retrieval.rerank_provider import (
    RerankItem,
    get_rerank_provider,
)


@dataclass(slots=True)
class Candidate:
    chunk: Chunk
    document: Document
    source: Source
    score_lexical: float
    score_dense: float
    score_authority: float
    score_freshness: float
    score_total: float


class SearchContextService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = Settings()

    def search_context(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        query: str,
        task_type: str | None = None,
        top_k: int = 5,
        user_id: uuid.UUID | None = None,
    ) -> dict:
        normalized_query = " ".join(query.lower().split())
        query_log = QueryLog(
            tenant_id=tenant_id,
            repo_id=repo_id,
            user_id=user_id,
            query_text=query,
            task_type=task_type,
            normalized_query=normalized_query,
            filters={"repo_id": str(repo_id) if repo_id else None, "top_k": top_k},
        )
        self.session.add(query_log)
        self.session.flush()

        candidates = self._retrieve_candidates(
            tenant_id=tenant_id,
            repo_id=repo_id,
            normalized_query=normalized_query,
            limit=max(top_k, 8),
        )
        candidates = self._rerank_candidates(normalized_query, candidates)[:top_k]

        evidence: list[dict] = []
        for rank, candidate in enumerate(candidates, start=1):
            why_selected = self._why_selected(candidate)
            freshness_reason = self._freshness_reason(candidate.source)
            evidence_item = build_evidence_item(
                chunk=candidate.chunk,
                document=candidate.document,
                source=candidate.source,
                why_selected=why_selected,
                freshness_reason=freshness_reason,
            )
            evidence.append(evidence_item)
            self.session.add(
                QueryResult(
                    query_log_id=query_log.id,
                    rank=rank,
                    chunk_id=candidate.chunk.id,
                    score_total=candidate.score_total,
                    score_lexical=candidate.score_lexical,
                    score_dense=candidate.score_dense,
                    score_graph=None,
                    score_freshness=candidate.score_freshness,
                    score_authority=candidate.score_authority,
                    score_version_match=None,
                    why_selected=why_selected,
                    evidence_payload=evidence_item,
                    authority=candidate.chunk.authority,
                    freshness_reason=freshness_reason,
                )
            )

        query_log.result_count = len(evidence)
        query_log.latency_ms = 0
        self.session.commit()
        return {
            "task_type": task_type or "locate",
            "clarify_needed": False,
            "evidence": evidence,
            "conflicts": [],
            "gaps": [],
        }

    def _retrieve_candidates(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        normalized_query: str,
        limit: int,
    ) -> list[Candidate]:
        ts_query = func.plainto_tsquery("simple", normalized_query)
        lexical_stmt = (
            select(
                Chunk,
                Document,
                Source,
                cast(
                    func.ts_rank_cd(
                        func.to_tsvector(
                            "simple",
                            func.concat_ws(" ", Chunk.context_prefix, Chunk.text),
                        ),
                        ts_query,
                    ),
                    Float,
                ).label("score_lexical"),
            )
            .join(Document, Document.id == Chunk.document_id)
            .join(Source, Source.id == Chunk.source_id)
            .where(Chunk.tenant_id == tenant_id)
            .where(Chunk.repo_id == repo_id if repo_id else Chunk.repo_id.is_(None))
            .order_by(
                func.ts_rank_cd(
                    func.to_tsvector(
                        "simple",
                        func.concat_ws(" ", Chunk.context_prefix, Chunk.text),
                    ),
                    ts_query,
                ).desc()
            )
            .limit(limit * 3)
        )

        lexical_rows = self.session.execute(lexical_stmt).all()
        query_embedding = embed_text(normalized_query, self.settings)
        candidates: list[Candidate] = []

        for chunk, document, source, score_lexical in lexical_rows:
            chunk_embedding = (
                list(chunk.embedding)
                if chunk.embedding is not None
                else embed_text(chunk.text, self.settings)
            )
            score_dense = cosine_similarity(query_embedding, chunk_embedding)
            score_authority = 1.0 if chunk.authority in {"repo", "official"} else 0.5
            score_freshness = 1.0 if source.updated_at_source else 0.6
            score_total = (
                (float(score_lexical) * 0.6)
                + (score_dense * 0.25)
                + (score_authority * 0.1)
                + (score_freshness * 0.05)
            )
            candidates.append(
                Candidate(
                    chunk=chunk,
                    document=document,
                    source=source,
                    score_lexical=float(score_lexical or 0.0),
                    score_dense=score_dense,
                    score_authority=score_authority,
                    score_freshness=score_freshness,
                    score_total=score_total,
                )
            )

        if candidates:
            candidates.sort(key=lambda item: item.score_total, reverse=True)
            return candidates

        fallback_stmt = (
            select(Chunk, Document, Source)
            .join(Document, Document.id == Chunk.document_id)
            .join(Source, Source.id == Chunk.source_id)
            .where(Chunk.tenant_id == tenant_id)
            .where(Chunk.repo_id == repo_id if repo_id else Chunk.repo_id.is_(None))
            .limit(limit * 3)
        )
        fallback_rows = self.session.execute(fallback_stmt).all()
        for chunk, document, source in fallback_rows:
            score_dense = cosine_similarity(
                query_embedding,
                (
                    list(chunk.embedding)
                    if chunk.embedding is not None
                    else embed_text(chunk.text, self.settings)
                ),
            )
            candidates.append(
                Candidate(
                    chunk=chunk,
                    document=document,
                    source=source,
                    score_lexical=0.0,
                    score_dense=score_dense,
                    score_authority=1.0 if chunk.authority in {"repo", "official"} else 0.5,
                    score_freshness=1.0 if source.updated_at_source else 0.6,
                    score_total=score_dense,
                )
            )
        candidates.sort(key=lambda item: item.score_total, reverse=True)
        return candidates

    def _rerank_candidates(self, query: str, candidates: list[Candidate]) -> list[Candidate]:
        provider = get_rerank_provider(self.settings)
        items = [
            RerankItem(
                item_id=str(candidate.chunk.id),
                text=f"{candidate.chunk.context_prefix}\n{candidate.chunk.text}",
                base_score=candidate.score_total,
            )
            for candidate in candidates
        ]
        reranked = provider.rerank(query, items)
        by_id = {str(candidate.chunk.id): candidate for candidate in candidates}
        ordered = [by_id[item.item_id] for item in reranked if item.item_id in by_id]
        return ordered or candidates

    def _why_selected(self, candidate: Candidate) -> str:
        reasons: list[str] = []
        if candidate.score_lexical > 0:
            reasons.append("Signal: lexical match")
        if candidate.score_dense > 0:
            reasons.append("Signal: semantic match")
        file_path = candidate.source.path_or_url
        if file_path:
            reasons.append(f"Source path: {file_path}")
        return "; ".join(reasons) or "Signal: ranked retrieval"

    def _freshness_reason(self, source: Source) -> str:
        if source.updated_at_source:
            timestamp = source.updated_at_source.astimezone(UTC).strftime("%Y-%m-%d")
            return f"Freshness: upstream timestamp {timestamp}"
        return "Freshness: repository content from latest local ingest snapshot"
