from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

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
        items: list[dict],
        acl_scope: dict,
    ) -> int:
        count = 0

        for item in items:
            source_type = item["source_type"]
            external_ref = item["external_ref"]
            title = item["title"]
            body = item.get("body", "")
            raw_text = f"{title}\n\n{body}".strip()
            metadata = {
                "author": item.get("author"),
                "labels": item.get("labels", []),
                "merged_at": item.get("merged_at"),
                "related_paths": item.get("related_paths", []),
            }

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
                checksum=_checksum(raw_text),
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
        acl_scope: dict,
    ) -> int:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        return self.ingest_items(
            tenant_id=tenant_id,
            repo_id=repo_id,
            items=payload,
            acl_scope=acl_scope,
        )


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
