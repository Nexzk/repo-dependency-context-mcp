"""initial schema

Revision ID: 20260322_0001
Revises:
Create Date: 2026-03-22 12:30:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


revision = "20260322_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "tenants",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("name", name=op.f("uq_tenants_name")),
        sa.UniqueConstraint("slug", name=op.f("uq_tenants_slug")),
    )

    op.create_table(
        "users",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("acl_scope", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_users_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_tenant_id"), "users", ["tenant_id"], unique=False)

    op.create_table(
        "repos",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("default_branch", sa.String(length=255), server_default="main", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("acl_scope", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_repos_tenant_id_tenants"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_repos")),
        sa.UniqueConstraint("tenant_id", "external_id", name=op.f("uq_repos_tenant_id")),
    )
    op.create_index(op.f("ix_repos_tenant_id"), "repos", ["tenant_id"], unique=False)

    op.create_table(
        "repo_memberships",
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=64), server_default="reader", nullable=False),
        sa.Column("acl_scope", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], name=op.f("fk_repo_memberships_repo_id_repos"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_repo_memberships_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_repo_memberships")),
        sa.UniqueConstraint("repo_id", "user_id", name=op.f("uq_repo_memberships_repo_id")),
    )
    op.create_index(op.f("ix_repo_memberships_repo_id"), "repo_memberships", ["repo_id"], unique=False)
    op.create_index(op.f("ix_repo_memberships_user_id"), "repo_memberships", ["user_id"], unique=False)

    op.create_table(
        "sources",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("authority", sa.String(length=64), nullable=False),
        sa.Column("path_or_url", sa.Text(), nullable=False),
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        sa.Column("version_range", sa.String(length=255), nullable=True),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("doc_version", sa.String(length=64), nullable=True),
        sa.Column("updated_at_source", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acl_scope", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], name=op.f("fk_sources_repo_id_repos"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
    )
    op.create_index(op.f("ix_sources_tenant_id"), "sources", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_sources_repo_id"), "sources", ["repo_id"], unique=False)
    op.create_index("ix_sources_tenant_repo_source_type", "sources", ["tenant_id", "repo_id", "source_type"], unique=False)

    op.create_table(
        "documents",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("section_title", sa.String(length=512), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=64), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], name=op.f("fk_documents_repo_id_repos"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name=op.f("fk_documents_source_id_sources"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("source_id", "checksum", name=op.f("uq_documents_source_id")),
    )
    op.create_index(op.f("ix_documents_tenant_id"), "documents", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_documents_repo_id"), "documents", ["repo_id"], unique=False)
    op.create_index(op.f("ix_documents_source_id"), "documents", ["source_id"], unique=False)

    op.create_table(
        "chunks",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_type", sa.String(length=64), nullable=False),
        sa.Column("symbol_path", sa.String(length=512), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("context_prefix", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding", Vector(dim=1536), nullable=True),
        sa.Column("fts", postgresql.TSVECTOR(), nullable=True),
        sa.Column("authority", sa.String(length=64), nullable=False),
        sa.Column("version_range", sa.String(length=255), nullable=True),
        sa.Column("updated_at_source", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acl_scope", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name=op.f("fk_chunks_document_id_documents"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], name=op.f("fk_chunks_repo_id_repos"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name=op.f("fk_chunks_source_id_sources"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
        sa.UniqueConstraint("document_id", "chunk_index", name=op.f("uq_chunks_document_id")),
    )
    op.create_index(op.f("ix_chunks_tenant_id"), "chunks", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_chunks_repo_id"), "chunks", ["repo_id"], unique=False)
    op.create_index(op.f("ix_chunks_document_id"), "chunks", ["document_id"], unique=False)
    op.create_index(op.f("ix_chunks_source_id"), "chunks", ["source_id"], unique=False)
    op.create_index("ix_chunks_tenant_repo_authority", "chunks", ["tenant_id", "repo_id", "authority"], unique=False)
    op.create_index("ix_chunks_fts", "chunks", ["fts"], unique=False, postgresql_using="gin")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunks_embedding_ivfflat "
        "ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )

    op.create_table(
        "symbols",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol_name", sa.String(length=255), nullable=False),
        sa.Column("symbol_kind", sa.String(length=64), nullable=False),
        sa.Column("symbol_path", sa.String(length=512), nullable=False),
        sa.Column("parent_symbol_path", sa.String(length=512), nullable=True),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("signature", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], name=op.f("fk_symbols_document_id_documents"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], name=op.f("fk_symbols_repo_id_repos"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_symbols")),
    )
    op.create_index(op.f("ix_symbols_tenant_id"), "symbols", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_symbols_repo_id"), "symbols", ["repo_id"], unique=False)
    op.create_index(op.f("ix_symbols_document_id"), "symbols", ["document_id"], unique=False)
    op.create_index("ix_symbols_repo_symbol_path", "symbols", ["repo_id", "symbol_path"], unique=False)

    op.create_table(
        "dependencies",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_name", sa.String(length=255), nullable=False),
        sa.Column("ecosystem", sa.String(length=64), nullable=False),
        sa.Column("declared_version", sa.String(length=255), nullable=False),
        sa.Column("resolved_version", sa.String(length=255), nullable=True),
        sa.Column("manager", sa.String(length=64), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], name=op.f("fk_dependencies_repo_id_repos"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dependencies")),
    )
    op.create_index(op.f("ix_dependencies_tenant_id"), "dependencies", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_dependencies_repo_id"), "dependencies", ["repo_id"], unique=False)
    op.create_index("ix_dependencies_repo_package_name", "dependencies", ["repo_id", "package_name"], unique=False)

    op.create_table(
        "dependency_docs",
        sa.Column("package_name", sa.String(length=255), nullable=False),
        sa.Column("ecosystem", sa.String(length=64), nullable=False),
        sa.Column("doc_type", sa.String(length=64), nullable=False),
        sa.Column("authority", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("version_range", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("section_title", sa.String(length=512), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dependency_docs")),
        sa.UniqueConstraint("url", name=op.f("uq_dependency_docs_url")),
    )
    op.create_index(op.f("ix_dependency_docs_package_name"), "dependency_docs", ["package_name"], unique=False)

    op.create_table(
        "ingest_jobs",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=64), server_default="pending", nullable=False),
        sa.Column("item_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failure_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("is_idempotent", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], name=op.f("fk_ingest_jobs_repo_id_repos"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], name=op.f("fk_ingest_jobs_source_id_sources"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingest_jobs")),
    )
    op.create_index(op.f("ix_ingest_jobs_tenant_id"), "ingest_jobs", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_ingest_jobs_repo_id"), "ingest_jobs", ["repo_id"], unique=False)
    op.create_index(op.f("ix_ingest_jobs_source_id"), "ingest_jobs", ["source_id"], unique=False)

    op.create_table(
        "query_logs",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=True),
        sa.Column("normalized_query", sa.Text(), nullable=True),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("result_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("clarify_needed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], name=op.f("fk_query_logs_repo_id_repos"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_query_logs_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_query_logs")),
    )
    op.create_index(op.f("ix_query_logs_tenant_id"), "query_logs", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_query_logs_repo_id"), "query_logs", ["repo_id"], unique=False)
    op.create_index(op.f("ix_query_logs_user_id"), "query_logs", ["user_id"], unique=False)
    op.create_index("ix_query_logs_tenant_created_at", "query_logs", ["tenant_id", "created_at"], unique=False)

    op.create_table(
        "query_results",
        sa.Column("query_log_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("score_total", sa.Float(), nullable=False),
        sa.Column("score_lexical", sa.Float(), nullable=True),
        sa.Column("score_dense", sa.Float(), nullable=True),
        sa.Column("score_graph", sa.Float(), nullable=True),
        sa.Column("score_freshness", sa.Float(), nullable=True),
        sa.Column("score_authority", sa.Float(), nullable=True),
        sa.Column("score_version_match", sa.Float(), nullable=True),
        sa.Column("why_selected", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("authority", sa.String(length=64), nullable=True),
        sa.Column("freshness_reason", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["chunks.id"], name=op.f("fk_query_results_chunk_id_chunks"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["query_log_id"], ["query_logs.id"], name=op.f("fk_query_results_query_log_id_query_logs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_query_results")),
        sa.UniqueConstraint("query_log_id", "rank", name=op.f("uq_query_results_query_log_id")),
    )
    op.create_index(op.f("ix_query_results_query_log_id"), "query_results", ["query_log_id"], unique=False)
    op.create_index(op.f("ix_query_results_chunk_id"), "query_results", ["chunk_id"], unique=False)

    op.create_table(
        "eval_datasets",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_datasets")),
        sa.UniqueConstraint("name", name=op.f("uq_eval_datasets_name")),
    )

    op.create_table(
        "eval_cases",
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repo_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=True),
        sa.Column("expected_evidence", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["eval_datasets.id"], name=op.f("fk_eval_cases_dataset_id_eval_datasets"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], name=op.f("fk_eval_cases_repo_id_repos"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_cases")),
    )
    op.create_index(op.f("ix_eval_cases_dataset_id"), "eval_cases", ["dataset_id"], unique=False)
    op.create_index(op.f("ix_eval_cases_tenant_id"), "eval_cases", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_eval_cases_repo_id"), "eval_cases", ["repo_id"], unique=False)

    op.create_table(
        "eval_runs",
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=64), server_default="pending", nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["eval_datasets.id"], name=op.f("fk_eval_runs_dataset_id_eval_datasets"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_runs")),
    )
    op.create_index(op.f("ix_eval_runs_dataset_id"), "eval_runs", ["dataset_id"], unique=False)

    op.create_table(
        "eval_case_results",
        sa.Column("eval_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("eval_case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recall_at_k", sa.Float(), nullable=True),
        sa.Column("mrr", sa.Float(), nullable=True),
        sa.Column("leakage_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["eval_case_id"], ["eval_cases.id"], name=op.f("fk_eval_case_results_eval_case_id_eval_cases"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["eval_run_id"], ["eval_runs.id"], name=op.f("fk_eval_case_results_eval_run_id_eval_runs"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_case_results")),
    )
    op.create_index(op.f("ix_eval_case_results_eval_run_id"), "eval_case_results", ["eval_run_id"], unique=False)
    op.create_index(op.f("ix_eval_case_results_eval_case_id"), "eval_case_results", ["eval_case_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_eval_case_results_eval_case_id"), table_name="eval_case_results")
    op.drop_index(op.f("ix_eval_case_results_eval_run_id"), table_name="eval_case_results")
    op.drop_table("eval_case_results")
    op.drop_index(op.f("ix_eval_runs_dataset_id"), table_name="eval_runs")
    op.drop_table("eval_runs")
    op.drop_index(op.f("ix_eval_cases_repo_id"), table_name="eval_cases")
    op.drop_index(op.f("ix_eval_cases_tenant_id"), table_name="eval_cases")
    op.drop_index(op.f("ix_eval_cases_dataset_id"), table_name="eval_cases")
    op.drop_table("eval_cases")
    op.drop_table("eval_datasets")
    op.drop_index(op.f("ix_query_results_chunk_id"), table_name="query_results")
    op.drop_index(op.f("ix_query_results_query_log_id"), table_name="query_results")
    op.drop_table("query_results")
    op.drop_index("ix_query_logs_tenant_created_at", table_name="query_logs")
    op.drop_index(op.f("ix_query_logs_user_id"), table_name="query_logs")
    op.drop_index(op.f("ix_query_logs_repo_id"), table_name="query_logs")
    op.drop_index(op.f("ix_query_logs_tenant_id"), table_name="query_logs")
    op.drop_table("query_logs")
    op.drop_index(op.f("ix_ingest_jobs_source_id"), table_name="ingest_jobs")
    op.drop_index(op.f("ix_ingest_jobs_repo_id"), table_name="ingest_jobs")
    op.drop_index(op.f("ix_ingest_jobs_tenant_id"), table_name="ingest_jobs")
    op.drop_table("ingest_jobs")
    op.drop_index(op.f("ix_dependency_docs_package_name"), table_name="dependency_docs")
    op.drop_table("dependency_docs")
    op.drop_index("ix_dependencies_repo_package_name", table_name="dependencies")
    op.drop_index(op.f("ix_dependencies_repo_id"), table_name="dependencies")
    op.drop_index(op.f("ix_dependencies_tenant_id"), table_name="dependencies")
    op.drop_table("dependencies")
    op.drop_index("ix_symbols_repo_symbol_path", table_name="symbols")
    op.drop_index(op.f("ix_symbols_document_id"), table_name="symbols")
    op.drop_index(op.f("ix_symbols_repo_id"), table_name="symbols")
    op.drop_index(op.f("ix_symbols_tenant_id"), table_name="symbols")
    op.drop_table("symbols")
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding_ivfflat")
    op.drop_index("ix_chunks_fts", table_name="chunks")
    op.drop_index("ix_chunks_tenant_repo_authority", table_name="chunks")
    op.drop_index(op.f("ix_chunks_source_id"), table_name="chunks")
    op.drop_index(op.f("ix_chunks_document_id"), table_name="chunks")
    op.drop_index(op.f("ix_chunks_repo_id"), table_name="chunks")
    op.drop_index(op.f("ix_chunks_tenant_id"), table_name="chunks")
    op.drop_table("chunks")
    op.drop_index(op.f("ix_documents_source_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_repo_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_tenant_id"), table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_sources_tenant_repo_source_type", table_name="sources")
    op.drop_index(op.f("ix_sources_repo_id"), table_name="sources")
    op.drop_index(op.f("ix_sources_tenant_id"), table_name="sources")
    op.drop_table("sources")
    op.drop_index(op.f("ix_repo_memberships_user_id"), table_name="repo_memberships")
    op.drop_index(op.f("ix_repo_memberships_repo_id"), table_name="repo_memberships")
    op.drop_table("repo_memberships")
    op.drop_index(op.f("ix_repos_tenant_id"), table_name="repos")
    op.drop_table("repos")
    op.drop_index(op.f("ix_users_tenant_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("tenants")
