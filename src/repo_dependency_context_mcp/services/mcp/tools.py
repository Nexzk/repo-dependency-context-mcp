from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from repo_dependency_context_mcp.db.models import (
    Chunk,
    Dependency,
    DependencyDoc,
    Document,
    QueryLog,
    Source,
)
from repo_dependency_context_mcp.services.retrieval.search import SearchContextService

JSONDict = dict[str, Any]
RelatedChangeItem = dict[str, Any]


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
    ) -> JSONDict:
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
    ) -> JSONDict:
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
    ) -> JSONDict:
        query = self._expand_related_change_query(
            tenant_id=tenant_id,
            repo_id=repo_id,
            path_or_symbol=path_or_symbol,
        )
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

        result: dict[str, list[RelatedChangeItem]] = {
            "pull_requests": [],
            "commits": [],
            "issues": [],
        }
        ranked_items: dict[str, list[tuple[tuple[int, float, str], RelatedChangeItem]]] = {
            "pull_requests": [],
            "commits": [],
            "issues": [],
        }
        for chunk, document, source in rows:
            match = _score_related_change(chunk=chunk, document=document, query=query)
            if match is None:
                continue
            merged_at = chunk.metadata_json.get("merged_at")
            merged_at_ts = 0.0
            if merged_at:
                try:
                    merged_at_dt = datetime.fromisoformat(merged_at.replace("Z", "+00:00"))
                    if merged_at_dt < cutoff:
                        continue
                    merged_at_ts = merged_at_dt.timestamp()
                except ValueError:
                    pass

            item: RelatedChangeItem = {
                "title": document.title,
                "external_ref": source.external_ref,
                "summary": chunk.text[:500],
                "author": chunk.metadata_json.get("author"),
                "labels": chunk.metadata_json.get("labels", []),
                "merged_at": chunk.metadata_json.get("merged_at"),
                "path_or_url": source.path_or_url,
                "related_file_paths": _related_file_paths(chunk.metadata_json),
                "related_symbols": _related_symbols(chunk.metadata_json),
                "source_pr_ref": chunk.metadata_json.get("source_pr_ref"),
                "source_commit_sha": chunk.metadata_json.get("source_commit_sha"),
                "source_commit_ref": chunk.metadata_json.get("source_commit_ref"),
                "source_issue_ref": chunk.metadata_json.get("source_issue_ref"),
                "match_kind": match.kind,
                "match_evidence": match.evidence,
            }
            if source.source_type == "pr":
                ranked_items["pull_requests"].append(
                    ((match.rank, merged_at_ts, source.external_ref or ""), item)
                )
            elif source.source_type == "commit":
                ranked_items["commits"].append(
                    ((match.rank, merged_at_ts, source.external_ref or ""), item)
                )
            elif source.source_type == "issue":
                ranked_items["issues"].append(
                    ((match.rank, merged_at_ts, source.external_ref or ""), item)
                )
        for key, values in ranked_items.items():
            values.sort(key=lambda pair: (-pair[0][0], -pair[0][1], pair[0][2]))
            result[key] = [item for _, item in values]
        return result

    def _expand_related_change_query(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID,
        path_or_symbol: str,
    ) -> "_RelatedChangeQuery":
        query = _parse_related_change_query(path_or_symbol)
        stmt = (
            select(Chunk, Source.path_or_url)
            .join(Source, Source.id == Chunk.source_id)
            .where(Chunk.tenant_id == tenant_id)
            .where(Chunk.repo_id == repo_id)
            .where(Source.source_type == "repo_code")
        )
        rows = self.session.execute(stmt).all()
        direct_path = _normalize_value(query.path)
        direct_symbol = _normalize_value(query.symbol)
        expanded_paths: set[str] = set()
        expanded_symbols: set[str] = set()

        for chunk, path_or_url in rows:
            normalized_path = _normalize_value(path_or_url)
            symbol_variants = _chunk_symbol_variants(chunk)

            if direct_path and normalized_path == direct_path:
                expanded_symbols.update(symbol_variants)
            if direct_symbol and direct_symbol in symbol_variants:
                expanded_paths.add(normalized_path)

        if direct_path:
            expanded_paths.discard(direct_path)
        if direct_symbol:
            expanded_symbols.discard(direct_symbol)

        return _RelatedChangeQuery(
            raw=query.raw,
            path=query.path,
            symbol=query.symbol,
            lexical_terms=query.lexical_terms,
            expanded_paths=sorted(expanded_paths),
            expanded_symbols=sorted(expanded_symbols),
        )

    def get_dependency_notes(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        package_name: str,
        version_range: str | None = None,
        topic: str | None = None,
        top_k: int = 5,
    ) -> JSONDict:
        stmt = select(DependencyDoc).where(DependencyDoc.package_name == package_name)
        if version_range:
            stmt = stmt.where(
                or_(
                    DependencyDoc.version_range == version_range,
                    DependencyDoc.version_range.is_(None),
                )
            )
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

        if repo_id is not None:
            repo_doc_stmt = (
                select(Document, Source)
                .join(Source, Source.id == Document.source_id)
                .where(Document.tenant_id == tenant_id)
                .where(Document.repo_id == repo_id)
                .where(Source.source_type == "repo_doc")
            )
            repo_docs = self.session.execute(repo_doc_stmt).all()
            for document, source in repo_docs:
                searchable = " ".join(
                    [
                        document.title or "",
                        document.section_title or "",
                        document.raw_text,
                    ]
                ).lower()
                if package_name.lower() not in searchable:
                    continue
                if topic and topic.lower() not in searchable:
                    continue
                evidence.append(
                    {
                        "source_type": "repo_doc",
                        "title": document.title,
                        "path_or_url": source.path_or_url,
                        "symbol_path": None,
                        "snippet": document.raw_text[:500],
                        "why_selected": self._why_selected_repo_doc(
                            document=document,
                            package_name=package_name,
                            topic=topic,
                        ),
                        "freshness_reason": (
                            "Freshness: internal repository note from latest local ingest snapshot"
                        ),
                        "authority": "repo",
                        "version_range": None,
                    }
                )

        if repo_id is not None:
            dep_stmt = (
                select(Dependency)
                .where(Dependency.tenant_id == tenant_id)
                .where(Dependency.repo_id == repo_id)
                .where(Dependency.package_name == package_name)
            )
            repo_dependencies = self.session.scalars(dep_stmt.limit(top_k)).all()
            for dependency in repo_dependencies:
                evidence.append(
                    {
                        "source_type": "dependency_manifest",
                        "title": f"{dependency.package_name} dependency declaration",
                        "path_or_url": str(
                            dependency.metadata_json.get("source_file", "<unknown-manifest>")
                        ),
                        "symbol_path": None,
                        "snippet": (
                            f"{dependency.package_name} {dependency.declared_version} "
                            f"declared via {dependency.manager}"
                        ),
                        "why_selected": self._why_selected_repo_dependency(
                            dependency=dependency,
                            topic=topic,
                        ),
                        "freshness_reason": (
                            "Freshness: repository dependency declaration "
                            "from latest local ingest snapshot"
                        ),
                        "authority": "repo",
                        "version_range": dependency.declared_version,
                    }
                )

        self.session.add(
            QueryLog(
                tenant_id=tenant_id,
                repo_id=repo_id,
                user_id=None,
                query_text=f"dependency:{package_name}:{topic or ''}",
                task_type="migration",
                normalized_query=f"{package_name} {topic or ''}".strip(),
                filters={
                    "package_name": package_name,
                    "version_range": version_range,
                    "top_k": top_k,
                },
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

    def _why_selected_repo_doc(
        self,
        document: Document,
        package_name: str,
        topic: str | None,
    ) -> str:
        reasons = [f"Matches package {package_name}"]
        if document.title:
            reasons.append(f"Internal note {document.title}")
        if topic:
            reasons.append(f"Context topic {topic}")
        return "; ".join(reasons)

    def _why_selected_repo_dependency(self, dependency: Dependency, topic: str | None) -> str:
        reasons = [f"Matches package {dependency.package_name}"]
        source_file = dependency.metadata_json.get("source_file")
        if source_file:
            reasons.append(f"Declared in {source_file}")
        if topic:
            reasons.append(f"Context topic {topic}")
        return "; ".join(reasons)


class _RelatedChangeQuery:
    def __init__(
        self,
        raw: str,
        path: str | None,
        symbol: str | None,
        lexical_terms: list[str],
        expanded_paths: list[str] | None = None,
        expanded_symbols: list[str] | None = None,
    ) -> None:
        self.raw = raw
        self.path = path
        self.symbol = symbol
        self.lexical_terms = lexical_terms
        self.expanded_paths = expanded_paths or []
        self.expanded_symbols = expanded_symbols or []


class _RelatedChangeMatch:
    def __init__(self, rank: int, kind: str, evidence: list[str]) -> None:
        self.rank = rank
        self.kind = kind
        self.evidence = evidence


def _parse_related_change_query(path_or_symbol: str) -> _RelatedChangeQuery:
    path = None
    symbol = None
    if ":" in path_or_symbol:
        left, right = path_or_symbol.split(":", 1)
        path = left.strip() or None
        symbol = right.strip() or None
    elif "/" in path_or_symbol or "." in path_or_symbol:
        path = path_or_symbol.strip() or None
    else:
        symbol = path_or_symbol.strip() or None

    lexical_terms = sorted(
        {
            term.lower()
            for term in re.split(r"[^A-Za-z0-9]+", path_or_symbol)
            if term and len(term) >= 2
        }
    )
    return _RelatedChangeQuery(
        raw=path_or_symbol,
        path=path,
        symbol=symbol,
        lexical_terms=lexical_terms,
    )


def _score_related_change(
    chunk: Chunk,
    document: Document,
    query: _RelatedChangeQuery,
) -> _RelatedChangeMatch | None:
    related_file_paths = [
        _normalize_value(value) for value in _related_file_paths(chunk.metadata_json)
    ]
    related_symbols = [_normalize_value(value) for value in _related_symbols(chunk.metadata_json)]
    related_paths = [
        _normalize_value(value)
        for value in chunk.metadata_json.get("related_paths", [])
    ]
    direct_path = _normalize_value(query.path)
    direct_symbol = _normalize_value(query.symbol)
    path_match = bool(direct_path and direct_path in (related_file_paths or related_paths))
    symbol_match = bool(direct_symbol and direct_symbol in (related_symbols or related_paths))
    expanded_path_hits = [
        expanded_path
        for expanded_path in query.expanded_paths
        if expanded_path in (related_file_paths or related_paths)
    ]
    expanded_symbol_hits = [
        expanded_symbol
        for expanded_symbol in query.expanded_symbols
        if expanded_symbol in (related_symbols or related_paths)
    ]
    expanded_path_match = bool(
        query.expanded_paths and expanded_path_hits
    )
    expanded_symbol_match = bool(
        query.expanded_symbols and expanded_symbol_hits
    )

    searchable = " ".join(
        [
            document.title or "",
            chunk.text,
            " ".join(chunk.metadata_json.get("related_paths", [])),
            " ".join(_related_file_paths(chunk.metadata_json)),
            " ".join(_related_symbols(chunk.metadata_json)),
        ]
    ).lower()
    lexical_match = any(term in searchable for term in query.lexical_terms)

    if path_match and not symbol_match:
        return _RelatedChangeMatch(
            rank=6,
            kind="direct_path",
            evidence=[f"path:{query.path}"],
        )
    if symbol_match and not path_match:
        return _RelatedChangeMatch(
            rank=5,
            kind="direct_symbol",
            evidence=[f"symbol:{query.symbol}"],
        )
    if path_match and symbol_match:
        return _RelatedChangeMatch(
            rank=4,
            kind="direct_path_and_symbol",
            evidence=[f"path:{query.path}", f"symbol:{query.symbol}"],
        )
    if expanded_path_match or expanded_symbol_match:
        evidence = [f"expanded_path:{value}" for value in expanded_path_hits]
        evidence.extend(f"expanded_symbol:{value}" for value in expanded_symbol_hits)
        return _RelatedChangeMatch(rank=3, kind="graph_expanded", evidence=evidence)
    if lexical_match:
        lexical_hits = [term for term in query.lexical_terms if term in searchable]
        return _RelatedChangeMatch(
            rank=2,
            kind="lexical",
            evidence=[f"lexical:{term}" for term in lexical_hits[:3]],
        )
    return None


def _normalize_value(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip().replace("\\", "/").lower()


def _chunk_symbol_variants(chunk: Chunk) -> set[str]:
    variants = set()
    for raw_value in [chunk.symbol_path, chunk.metadata_json.get("symbol_name")]:
        normalized = _normalize_value(raw_value)
        if not normalized:
            continue
        variants.add(normalized)
        variants.add(normalized.split(".")[-1])
        variants.add(normalized.split("::")[-1])
    return {value for value in variants if value}


def _related_file_paths(metadata: JSONDict) -> list[str]:
    explicit = [str(value) for value in metadata.get("related_file_paths", [])]
    if explicit:
        return explicit
    return [
        str(value)
        for value in metadata.get("related_paths", [])
        if "/" in str(value) or "." in str(value)
    ]


def _related_symbols(metadata: JSONDict) -> list[str]:
    explicit = [str(value) for value in metadata.get("related_symbols", [])]
    if explicit:
        return explicit
    return [
        str(value)
        for value in metadata.get("related_paths", [])
        if "/" not in str(value) and "." not in str(value)
    ]
