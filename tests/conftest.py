import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from repo_dependency_context_mcp.config import Settings
from repo_dependency_context_mcp.db.session import create_engine, create_session_factory

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


os.environ.setdefault("RDCMCP_APP_NAME", "repo-dependency-context-mcp")
os.environ.setdefault("RDCMCP_ENV", "test")
os.environ.setdefault("RDCMCP_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/rdcmcp")
os.environ.setdefault("RDCMCP_REDIS_URL", "redis://localhost:6379/0")

TEST_DB_LOCK_ID = 842021


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session")
def db_engine(settings: Settings):
    return create_engine(settings)


@pytest.fixture()
def db_session(db_engine) -> Session:
    table_names = [
        "eval_case_results",
        "eval_runs",
        "eval_cases",
        "eval_datasets",
        "query_results",
        "query_logs",
        "ingest_jobs",
        "symbols",
        "chunks",
        "documents",
        "dependency_docs",
        "dependencies",
        "sources",
        "repo_memberships",
        "repos",
        "users",
        "tenants",
    ]

    lock_connection = db_engine.connect()
    lock_connection.execute(text(f"SELECT pg_advisory_lock({TEST_DB_LOCK_ID})"))
    lock_connection.execute(text(f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE"))
    lock_connection.commit()

    session_factory = create_session_factory(Settings())
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        lock_connection.execute(text(f"SELECT pg_advisory_unlock({TEST_DB_LOCK_ID})"))
        lock_connection.close()
