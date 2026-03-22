from repo_dependency_context_mcp.db.base import Base
from repo_dependency_context_mcp.db.models import (  # noqa: F401
    Chunk,
    Dependency,
    DependencyDoc,
    Document,
    EvalCase,
    EvalCaseResult,
    EvalDataset,
    EvalRun,
    IngestJob,
    QueryLog,
    QueryResult,
    Repo,
    RepoMembership,
    Source,
    Symbol,
    Tenant,
    User,
)


def test_core_tables_are_registered() -> None:
    expected_tables = {
        "chunks",
        "dependencies",
        "dependency_docs",
        "documents",
        "eval_case_results",
        "eval_cases",
        "eval_datasets",
        "eval_runs",
        "ingest_jobs",
        "query_logs",
        "query_results",
        "repo_memberships",
        "repos",
        "sources",
        "symbols",
        "tenants",
        "users",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())


def test_chunk_table_has_acl_authority_and_uniqueness_guards() -> None:
    table = Base.metadata.tables["chunks"]

    assert "authority" in table.c
    assert "acl_scope" in table.c
    assert "context_prefix" in table.c
    assert any(
        constraint.columns.keys() == ["document_id", "chunk_index"]
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    )


def test_query_logging_schema_captures_selection_metadata() -> None:
    query_logs = Base.metadata.tables["query_logs"]
    query_results = Base.metadata.tables["query_results"]

    assert "filters" in query_logs.c
    assert "result_count" in query_logs.c
    assert "why_selected" in query_results.c
    assert any(
        constraint.columns.keys() == ["query_log_id", "rank"]
        for constraint in query_results.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    )
