from __future__ import annotations

import hashlib
import mimetypes
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from repo_dependency_context_mcp.db.models import Chunk, Document, IngestJob, Repo, Source
from repo_dependency_context_mcp.services.chunking.code import chunk_python_file
from repo_dependency_context_mcp.services.chunking.markdown import chunk_markdown_file
from repo_dependency_context_mcp.services.ingest.sync_state import SyncStateService
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
        sync_state = SyncStateService(self.session)
        scope_key = f"{repo_id}:working_tree"
        sync_run = sync_state.start_run(
            tenant_id=tenant_id,
            repo_id=repo_id,
            source_kind="local_repo",
            scope_key=scope_key,
            cursor_kind="repo_snapshot",
        )

        ingest_job = IngestJob(
            tenant_id=tenant_id,
            repo_id=repo_id,
            status="running",
            started_at=datetime.now(UTC),
            metadata_json={"repo_path": str(repo_path)},
        )
        self.session.add(ingest_job)
        self.session.commit()

        source_count = 0
        document_count = 0
        chunk_count = 0
        items_seen = 0
        snapshot_parts: list[str] = []

        try:
            for file_path in sorted(repo_path.rglob("*")):
                if not file_path.is_file() or file_path.suffix not in SUPPORTED_SUFFIXES:
                    continue

                items_seen += 1
                source_type, language = SUPPORTED_SUFFIXES[file_path.suffix]
                relative_path = file_path.relative_to(repo_path).as_posix()
                raw_text = file_path.read_text(encoding="utf-8")
                snapshot_parts.append(f"{relative_path}:{_checksum(raw_text)}")
                if not raw_text.strip():
                    continue
                checksum = _checksum(raw_text)
                source = self._get_existing_source(
                    tenant_id=tenant_id,
                    repo_id=repo_id,
                    source_type=source_type,
                    relative_path=relative_path,
                )
                if (
                    source is not None
                    and self._source_has_checksum(source_id=source.id, checksum=checksum)
                ):
                    continue

                if source is None:
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
                else:
                    source.acl_scope = acl_scope
                    source.metadata_json = {"language": language}
                    self._delete_source_documents(source_id=source.id)
                source_count += 1

                document = Document(
                    tenant_id=tenant_id,
                    repo_id=repo_id,
                    source_id=source.id,
                    title=relative_path,
                    section_title=None,
                    mime_type=_guess_mime_type(file_path, language),
                    language=language,
                    checksum=checksum,
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
        except Exception as exc:
            self.session.rollback()
            failed_job = self.session.get(IngestJob, ingest_job.id)
            if failed_job is not None:
                failed_job.item_count = source_count
                failed_job.chunk_count = chunk_count
                failed_job.failure_count = 1
                failed_job.status = "failed"
                failed_job.finished_at = datetime.now(UTC)
                self.session.commit()
            sync_state.mark_failure(sync_run, error=str(exc))
            raise

        ingest_job = self.session.get(IngestJob, ingest_job.id)
        if ingest_job is not None:
            ingest_job.item_count = source_count
            ingest_job.chunk_count = chunk_count
            ingest_job.status = "completed"
            ingest_job.finished_at = datetime.now(UTC)
        self.session.commit()
        sync_state.mark_success(
            run=sync_run,
            cursor_after=_repo_snapshot(snapshot_parts),
            items_seen=items_seen,
            items_written=source_count,
        )
        return IngestSummary(
            source_count=source_count,
            document_count=document_count,
            chunk_count=chunk_count,
        )

    def _get_repo_name(self, repo_id: uuid.UUID) -> str:
        row = self.session.execute(select(Repo.name).where(Repo.id == repo_id)).scalar_one()
        return str(row)

    def _get_existing_source(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID,
        source_type: str,
        relative_path: str,
    ) -> Source | None:
        return self.session.execute(
            select(Source).where(
                Source.tenant_id == tenant_id,
                Source.repo_id == repo_id,
                Source.source_type == source_type,
                Source.path_or_url == relative_path,
            )
        ).scalar_one_or_none()

    def _source_has_checksum(self, source_id: uuid.UUID, checksum: str) -> bool:
        existing_checksum = self.session.execute(
            select(Document.checksum).where(Document.source_id == source_id)
        ).scalar_one_or_none()
        return existing_checksum == checksum

    def _delete_source_documents(self, source_id: uuid.UUID) -> None:
        self.session.execute(delete(Document).where(Document.source_id == source_id))


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


def _repo_snapshot(snapshot_parts: list[str]) -> str:
    payload = "\n".join(sorted(snapshot_parts))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
