from __future__ import annotations

import hashlib
import mimetypes
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from repo_dependency_context_mcp.db.models import Chunk, Document, IngestJob, Repo, Source
from repo_dependency_context_mcp.services.chunking.code import chunk_python_file
from repo_dependency_context_mcp.services.chunking.markdown import chunk_markdown_file
from repo_dependency_context_mcp.services.retrieval.embedding import embed_text

SUPPORTED_SUFFIXES = {
    ".py": ("repo_code", "python"),
    ".md": ("repo_doc", "markdown"),
}


@dataclass(slots=True)
class IngestSummary:
    source_count: int
    document_count: int
    chunk_count: int


class LocalRepoIngestService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ingest_repo(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID,
        repo_path: Path,
        acl_scope: dict,
    ) -> IngestSummary:
        repo = self.session.get_bind()
        del repo

        ingest_job = IngestJob(
            tenant_id=tenant_id,
            repo_id=repo_id,
            status="running",
            metadata_json={"repo_path": str(repo_path)},
        )
        self.session.add(ingest_job)
        self.session.flush()

        source_count = 0
        document_count = 0
        chunk_count = 0

        for file_path in sorted(repo_path.rglob("*")):
            if not file_path.is_file() or file_path.suffix not in SUPPORTED_SUFFIXES:
                continue

            source_type, language = SUPPORTED_SUFFIXES[file_path.suffix]
            relative_path = file_path.relative_to(repo_path).as_posix()
            raw_text = file_path.read_text(encoding="utf-8")
            if not raw_text.strip():
                continue

            source = Source(
                tenant_id=tenant_id,
                repo_id=repo_id,
                source_type=source_type,
                authority="repo",
                path_or_url=relative_path,
                acl_scope=acl_scope,
                metadata_json={"language": language},
            )
            self.session.add(source)
            self.session.flush()
            source_count += 1

            document = Document(
                tenant_id=tenant_id,
                repo_id=repo_id,
                source_id=source.id,
                title=relative_path,
                section_title=None,
                mime_type=_guess_mime_type(file_path, language),
                language=language,
                checksum=_checksum(raw_text),
                raw_text=raw_text,
                metadata_json={"file_path": relative_path, "language": language},
            )
            self.session.add(document)
            self.session.flush()
            document_count += 1

            drafts = _chunk_file(
                repo_name=self._get_repo_name(repo_id),
                file_path=relative_path,
                language=language,
                raw_text=raw_text,
            )
            for index, draft in enumerate(drafts):
                chunk = Chunk(
                    tenant_id=tenant_id,
                    repo_id=repo_id,
                    document_id=document.id,
                    source_id=source.id,
                    chunk_index=index,
                    chunk_type=draft.chunk_type,
                    symbol_path=draft.symbol_path,
                    text=draft.text,
                    context_prefix=draft.context_prefix,
                    token_count=draft.token_count,
                    embedding=embed_text(f"{draft.context_prefix}\n{draft.text}"),
                    authority="repo",
                    acl_scope=acl_scope,
                    metadata_json=draft.metadata,
                )
                self.session.add(chunk)
                chunk_count += 1

        ingest_job.item_count = source_count
        ingest_job.chunk_count = chunk_count
        ingest_job.status = "completed"
        self.session.commit()
        return IngestSummary(
            source_count=source_count,
            document_count=document_count,
            chunk_count=chunk_count,
        )

    def _get_repo_name(self, repo_id: uuid.UUID) -> str:
        row = self.session.execute(select(Repo.name).where(Repo.id == repo_id)).scalar_one()
        return str(row)


def _chunk_file(repo_name: str, file_path: str, language: str, raw_text: str):
    if language == "python":
        return chunk_python_file(repo_name=repo_name, file_path=file_path, source_text=raw_text)
    if language == "markdown":
        return chunk_markdown_file(repo_name=repo_name, file_path=file_path, source_text=raw_text)
    return []


def _checksum(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def _guess_mime_type(file_path: Path, language: str) -> str:
    if language == "python":
        return "text/x-python"
    if language == "markdown":
        return "text/markdown"
    guessed, _ = mimetypes.guess_type(file_path.name)
    return guessed or "text/plain"
