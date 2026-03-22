from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from repo_dependency_context_mcp.db.models import Chunk, DependencyDoc, Document, QueryLog, Source
from repo_dependency_context_mcp.services.retrieval.search import SearchContextService


class MCPToolService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.search_service = SearchContextService(session)

    def search_context(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        query: str,
        task_type: str | None = None,
        top_k: int = 5,
    ) -> dict:
        return self.search_service.search_context(
            tenant_id=tenant_id,
            repo_id=repo_id,
            query=query,
            task_type=task_type,
            top_k=top_k,
        )

    def get_source(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID,
        path_or_url: str,
        start_line: int,
        end_line: int,
    ) -> dict:
        stmt = (
            select(Document, Source)
            .join(Source, Source.id == Document.source_id)
            .where(Document.tenant_id == tenant_id)
            .where(Document.repo_id == repo_id)
            .where(Source.path_or_url == path_or_url)
            .limit(1)
        )
        row = self.session.execute(stmt).first()
        if row is None:
            raise LookupError(f"source not found for {path_or_url}")

        document, source = row
        lines = document.raw_text.splitlines()
        selected = lines[max(start_line - 1, 0) : end_line]
        return {
            "path_or_url": path_or_url,
            "source_type": source.source_type,
            "title": document.title,
            "start_line": start_line,
            "end_line": end_line,
            "content": "\n".join(selected),
        }

    def get_related_changes(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID,
        path_or_symbol: str,
        since_days: int,
    ) -> dict:
        tokens = [part for part in path_or_symbol.replace(":", " ").split() if part]
        cutoff = datetime.now(UTC) - timedelta(days=since_days)
        stmt = (
            select(Chunk, Document, Source)
            .join(Document, Document.id == Chunk.document_id)
            .join(Source, Source.id == Chunk.source_id)
            .where(Chunk.tenant_id == tenant_id)
            .where(Chunk.repo_id == repo_id)
            .where(Source.source_type.in_(["pr", "commit", "issue"]))
        )
        rows = self.session.execute(stmt).all()

        result = {
            "pull_requests": [],
            "commits": [],
            "issues": [],
        }
        for chunk, document, source in rows:
            if not _matches_related_change(chunk=chunk, document=document, tokens=tokens):
                continue
            merged_at = chunk.metadata_json.get("merged_at")
            if merged_at:
                try:
                    merged_at_dt = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
                    if merged_at_dt < cutoff:
                        continue
                except ValueError:
                    pass

            item = {
                "title": document.title,
                "external_ref": source.external_ref,
                "summary": chunk.text[:500],
                "author": chunk.metadata_json.get("author"),
                "labels": chunk.metadata_json.get("labels", []),
                "merged_at": chunk.metadata_json.get("merged_at"),
                "path_or_url": source.path_or_url,
            }
            if source.source_type == "pr":
                result["pull_requests"].append(item)
            elif source.source_type == "commit":
                result["commits"].append(item)
            elif source.source_type == "issue":
                result["issues"].append(item)
        return result

    def get_dependency_notes(
        self,
        tenant_id: uuid.UUID,
        package_name: str,
        version_range: str | None = None,
        topic: str | None = None,
        top_k: int = 5,
    ) -> dict:
        stmt = select(DependencyDoc).where(DependencyDoc.package_name == package_name)
        if version_range:
            stmt = stmt.where(or_(DependencyDoc.version_range == version_range, DependencyDoc.version_range.is_(None)))
        docs = self.session.scalars(stmt.limit(top_k)).all()

        evidence = []
        for doc in docs:
            why_selected = self._why_selected_dependency_doc(doc=doc, topic=topic)
            freshness_reason = "Official vendor documentation ingested from whitelisted domain"
            evidence.append(
                {
                    "source_type": "vendor_doc",
                    "title": doc.title,
                    "path_or_url": doc.url,
                    "symbol_path": None,
                    "snippet": doc.raw_text[:500],
                    "why_selected": why_selected,
                    "freshness_reason": freshness_reason,
                    "authority": doc.authority,
                    "version_range": doc.version_range,
                }
            )

        self.session.add(
            QueryLog(
                tenant_id=tenant_id,
                repo_id=None,
                user_id=None,
                query_text=f"dependency:{package_name}:{topic or ''}",
                task_type="migration",
                normalized_query=f"{package_name} {topic or ''}".strip(),
                filters={"package_name": package_name, "version_range": version_range, "top_k": top_k},
                result_count=len(evidence),
                latency_ms=0,
            )
        )
        self.session.commit()
        return {
            "evidence": evidence,
            "conflicts": [],
            "gaps": [] if evidence else [f"No official dependency notes found for {package_name}"],
        }

    def _why_selected_dependency_doc(self, doc: DependencyDoc, topic: str | None) -> str:
        reasons = [f"Matches package {doc.package_name}"]
        if topic and topic.lower() in doc.raw_text.lower():
            reasons.append(f"Mentions topic {topic}")
        if doc.doc_type:
            reasons.append(f"Document type is {doc.doc_type}")
        return "; ".join(reasons)


def _matches_related_change(chunk: Chunk, document: Document, tokens: list[str]) -> bool:
    searchable = " ".join(
        [
            document.title or "",
            chunk.text,
            " ".join(chunk.metadata_json.get("related_paths", [])),
        ]
    ).lower()
    return any(token.lower() in searchable for token in tokens)
