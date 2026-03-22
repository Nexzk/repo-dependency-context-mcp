from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from repo_dependency_context_mcp.db.base import Base
from repo_dependency_context_mcp.db.models.common import TimestampMixin, UUIDPrimaryKeyMixin


class SyncCursor(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sync_cursors"
    __table_args__ = (
        UniqueConstraint("tenant_id", "repo_id", "source_kind", "scope_key"),
        Index("ix_sync_cursors_source_scope", "source_kind", "scope_key"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repos.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False)
    cursor_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    cursor_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class SyncRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sync_runs"
    __table_args__ = (
        Index("ix_sync_runs_tenant_repo_source_kind", "tenant_id", "repo_id", "source_kind"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repos.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", server_default="running")
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    items_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    items_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    cursor_before: Mapped[str | None] = mapped_column(Text, nullable=True)
    cursor_after: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")
