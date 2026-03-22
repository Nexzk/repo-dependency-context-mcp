from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from repo_dependency_context_mcp.db.base import Base
from repo_dependency_context_mcp.db.models.common import (
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    jsonb_column,
)

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover - local fallback when pgvector is unavailable
    from sqlalchemy import JSON

    class Vector(JSON):  # type: ignore[misc]
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            super().__init__()


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (
        Index("ix_sources_tenant_repo_source_type", "tenant_id", "repo_id", "source_type"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repos.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    authority: Mapped[str] = mapped_column(String(64), nullable=False)
    path_or_url: Mapped[str] = mapped_column(Text, nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    version_range: Mapped[str | None] = mapped_column(String(255), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    doc_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at_source: Mapped[datetime | None] = mapped_column(nullable=True)
    acl_scope: Mapped[dict] = jsonb_column()
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("source_id", "checksum"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repos.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")


class Chunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        Index("ix_chunks_tenant_repo_authority", "tenant_id", "repo_id", "authority"),
        Index("ix_chunks_fts", "fts", postgresql_using="gin"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repos.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    context_prefix: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    embedding: Mapped[object | None] = mapped_column(Vector(1536), nullable=True)
    fts: Mapped[str | None] = mapped_column(TSVECTOR, nullable=True)
    authority: Mapped[str] = mapped_column(String(64), nullable=False)
    version_range: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at_source: Mapped[datetime | None] = mapped_column(nullable=True)
    acl_scope: Mapped[dict] = jsonb_column()
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")


class Symbol(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "symbols"
    __table_args__ = (Index("ix_symbols_repo_symbol_path", "repo_id", "symbol_path"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol_name: Mapped[str] = mapped_column(String(255), nullable=False)
    symbol_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol_path: Mapped[str] = mapped_column(String(512), nullable=False)
    parent_symbol_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    signature: Mapped[str | None] = mapped_column(Text, nullable=True)


class Dependency(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dependencies"
    __table_args__ = (Index("ix_dependencies_repo_package_name", "repo_id", "package_name"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    package_name: Mapped[str] = mapped_column(String(255), nullable=False)
    ecosystem: Mapped[str] = mapped_column(String(64), nullable=False)
    declared_version: Mapped[str] = mapped_column(String(255), nullable=False)
    resolved_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manager: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")


class DependencyDoc(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dependency_docs"

    package_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ecosystem: Mapped[str] = mapped_column(String(64), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    authority: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    version_range: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    section_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")


class IngestJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ingest_jobs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repos.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="pending", server_default="pending")
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")
    is_idempotent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
