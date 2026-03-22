from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from repo_dependency_context_mcp.db.models import Chunk, Document, Source
from repo_dependency_context_mcp.services.retrieval.embedding import embed_text


class ChangeMetadataIngestService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ingest_items(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID,
        items: list[dict[str, Any]],
        acl_scope: dict[str, Any],
    ) -> int:
        count = 0

        for item in items:
            source_type = item["source_type"]
            external_ref = item["external_ref"]
            title = item["title"]
            body = item.get("body", "")
            raw_text = f"{title}\n\n{body}".strip()
            related_metadata = _normalize_related_metadata(item)
            metadata = {
                "author": item.get("author"),
                "labels": item.get("labels", []),
                "merged_at": item.get("merged_at"),
                **related_metadata,
                **_normalize_source_refs(source_type=source_type, external_ref=external_ref, item=item),
            }
            checksum = _checksum(raw_text)
            source = self.session.execute(
                select(Source).where(
                    Source.tenant_id == tenant_id,
                    Source.repo_id == repo_id,
                    Source.source_type == source_type,
                    Source.external_ref == external_ref,
                )
            ).scalar_one_or_none()
            if source is not None:
                existing_checksum = self.session.execute(
                    select(Document.checksum).where(Document.source_id == source.id)
                ).scalar_one_or_none()
                if existing_checksum == checksum:
                    continue
                source.path_or_url = f"{source_type}:{external_ref}"
                source.acl_scope = acl_scope
                source.metadata_json = metadata
                self._delete_source_documents(source_id=source.id)
            else:
                source = Source(
                    tenant_id=tenant_id,
                    repo_id=repo_id,
                    source_type=source_type,
                    authority="repo",
                    path_or_url=f"{source_type}:{external_ref}",
                    external_ref=external_ref,
                    acl_scope=acl_scope,
                    metadata_json=metadata,
                )
                self.session.add(source)
                self.session.flush()

            document = Document(
                tenant_id=tenant_id,
                repo_id=repo_id,
                source_id=source.id,
                title=title,
                section_title=None,
                mime_type="text/plain",
                language=None,
                checksum=checksum,
                raw_text=raw_text,
                metadata_json=metadata,
            )
            self.session.add(document)
            self.session.flush()

            context_prefix = _build_context_prefix(
                source_type=source_type,
                title=title,
                author=item.get("author"),
                merged_at=item.get("merged_at"),
            )
            chunk = Chunk(
                tenant_id=tenant_id,
                repo_id=repo_id,
                document_id=document.id,
                source_id=source.id,
                chunk_index=0,
                chunk_type=f"{source_type}_summary",
                symbol_path=None,
                text=raw_text,
                context_prefix=context_prefix,
                token_count=max(1, len(raw_text.split())),
                embedding=embed_text(f"{context_prefix}\n{raw_text}"),
                authority="repo",
                acl_scope=acl_scope,
                metadata_json=metadata,
            )
            self.session.add(chunk)
            count += 1

        self.session.commit()
        return count

    def ingest_json_fixture(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID,
        fixture_path: Path,
        acl_scope: dict[str, Any],
    ) -> int:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        return self.ingest_items(
            tenant_id=tenant_id,
            repo_id=repo_id,
            items=payload,
            acl_scope=acl_scope,
        )

    def _delete_source_documents(self, source_id: uuid.UUID) -> None:
        self.session.execute(delete(Document).where(Document.source_id == source_id))


def _checksum(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def _build_context_prefix(source_type: str, title: str, author: str | None, merged_at: str | None) -> str:
    lines = [
        f"SourceType: {source_type}",
        f"Title: {title}",
    ]
    if author:
        lines.append(f"Author: {author}")
    if merged_at:
        lines.append(f"MergedAt: {merged_at}")
    lines.append("This chunk contains related change metadata.")
    return "\n".join(lines)


def _normalize_related_metadata(item: dict[str, Any]) -> dict[str, Any]:
    related_paths = [str(value) for value in item.get("related_paths", [])]
    related_file_paths = [str(value) for value in item.get("related_file_paths", [])]
    related_symbols = [str(value) for value in item.get("related_symbols", [])]

    for value in related_paths:
        if "/" in value or "." in value:
            related_file_paths.append(value)
        else:
            related_symbols.append(value)

    normalized_file_paths = sorted(set(related_file_paths))
    normalized_symbols = sorted(set(related_symbols))
    return {
        "related_paths": sorted(set(related_paths or [*normalized_file_paths, *normalized_symbols])),
        "related_file_paths": normalized_file_paths,
        "related_symbols": normalized_symbols,
    }


def _normalize_source_refs(source_type: str, external_ref: str, item: dict[str, Any]) -> dict[str, Any]:
    refs = {
        "source_pr_ref": item.get("source_pr_ref"),
        "source_commit_sha": item.get("source_commit_sha"),
        "source_commit_ref": item.get("source_commit_ref"),
        "source_issue_ref": item.get("source_issue_ref"),
    }
    if source_type == "pr":
        refs["source_pr_ref"] = refs["source_pr_ref"] or external_ref
    elif source_type == "commit":
        refs["source_commit_sha"] = refs["source_commit_sha"] or external_ref
        refs["source_commit_ref"] = refs["source_commit_ref"] or external_ref
    elif source_type == "issue":
        refs["source_issue_ref"] = refs["source_issue_ref"] or external_ref
    return refs
