from __future__ import annotations

from contextlib import contextmanager

from repo_dependency_context_mcp.config import Settings
from repo_dependency_context_mcp.db.session import create_session_factory


def get_settings() -> Settings:
    return Settings()


@contextmanager
def get_db_session():
    session_factory = create_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
