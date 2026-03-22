from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from repo_dependency_context_mcp.db.base import Base
from repo_dependency_context_mcp.db.models.common import UUIDPrimaryKeyMixin, jsonb_column


class QueryLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "query_logs"
    __table_args__ = (Index("ix_query_logs_tenant_created_at", "tenant_id", "created_at"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalized_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    filters: Mapped[dict] = jsonb_column()
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    clarify_needed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class QueryResult(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "query_results"
    __table_args__ = (UniqueConstraint("query_log_id", "rank"),)

    query_log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("query_logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    score_total: Mapped[float] = mapped_column(Float, nullable=False)
    score_lexical: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_dense: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_graph: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_freshness: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_authority: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_version_match: Mapped[float | None] = mapped_column(Float, nullable=True)
    why_selected: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_payload: Mapped[dict] = mapped_column("evidence", JSONB, nullable=False, default=dict, server_default="{}")
    authority: Mapped[str | None] = mapped_column(String(64), nullable=True)
    freshness_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
