"""add query feedback table

Revision ID: 20260324_0003
Revises: 20260322_0002
Create Date: 2026-03-24 10:10:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260324_0003"
down_revision = "20260322_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "query_feedback",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("query_log_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("query_result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("feedback_type", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "expected_source_keys",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["query_log_id"],
            ["query_logs.id"],
            name=op.f("fk_query_feedback_query_log_id_query_logs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["query_result_id"],
            ["query_results.id"],
            name=op.f("fk_query_feedback_query_result_id_query_results"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["repo_id"],
            ["repos.id"],
            name=op.f("fk_query_feedback_repo_id_repos"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_query_feedback")),
    )
    op.create_index(op.f("ix_query_feedback_tenant_id"), "query_feedback", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_query_feedback_repo_id"), "query_feedback", ["repo_id"], unique=False)
    op.create_index(
        op.f("ix_query_feedback_query_log_id"),
        "query_feedback",
        ["query_log_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_query_feedback_query_result_id"),
        "query_feedback",
        ["query_result_id"],
        unique=False,
    )
    op.create_index(
        "ix_query_feedback_query_log_created_at",
        "query_feedback",
        ["query_log_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_query_feedback_tenant_created_at",
        "query_feedback",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_query_feedback_tenant_created_at", table_name="query_feedback")
    op.drop_index("ix_query_feedback_query_log_created_at", table_name="query_feedback")
    op.drop_index(op.f("ix_query_feedback_query_result_id"), table_name="query_feedback")
    op.drop_index(op.f("ix_query_feedback_query_log_id"), table_name="query_feedback")
    op.drop_index(op.f("ix_query_feedback_repo_id"), table_name="query_feedback")
    op.drop_index(op.f("ix_query_feedback_tenant_id"), table_name="query_feedback")
    op.drop_table("query_feedback")
