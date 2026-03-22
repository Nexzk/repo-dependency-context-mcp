"""add sync state tables

Revision ID: 20260322_0002
Revises: 20260322_0001
Create Date: 2026-03-22 20:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260322_0002"
down_revision = "20260322_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sync_cursors",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("cursor_kind", sa.String(length=64), nullable=False),
        sa.Column("cursor_value", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], name=op.f("fk_sync_cursors_repo_id_repos"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_cursors")),
        sa.UniqueConstraint(
            "tenant_id",
            "repo_id",
            "source_kind",
            "scope_key",
            name=op.f("uq_sync_cursors_tenant_id"),
        ),
    )
    op.create_index(op.f("ix_sync_cursors_tenant_id"), "sync_cursors", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_sync_cursors_repo_id"), "sync_cursors", ["repo_id"], unique=False)
    op.create_index(
        "ix_sync_cursors_source_scope",
        "sync_cursors",
        ["source_kind", "scope_key"],
        unique=False,
    )

    op.create_table(
        "sync_runs",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_kind", sa.String(length=64), nullable=False),
        sa.Column("scope_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="running", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("items_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("items_written", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cursor_before", sa.Text(), nullable=True),
        sa.Column("cursor_after", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], name=op.f("fk_sync_runs_repo_id_repos"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_runs")),
    )
    op.create_index(op.f("ix_sync_runs_tenant_id"), "sync_runs", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_sync_runs_repo_id"), "sync_runs", ["repo_id"], unique=False)
    op.create_index(
        "ix_sync_runs_tenant_repo_source_kind",
        "sync_runs",
        ["tenant_id", "repo_id", "source_kind"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sync_runs_tenant_repo_source_kind", table_name="sync_runs")
    op.drop_index(op.f("ix_sync_runs_repo_id"), table_name="sync_runs")
    op.drop_index(op.f("ix_sync_runs_tenant_id"), table_name="sync_runs")
    op.drop_table("sync_runs")

    op.drop_index("ix_sync_cursors_source_scope", table_name="sync_cursors")
    op.drop_index(op.f("ix_sync_cursors_repo_id"), table_name="sync_cursors")
    op.drop_index(op.f("ix_sync_cursors_tenant_id"), table_name="sync_cursors")
    op.drop_table("sync_cursors")
