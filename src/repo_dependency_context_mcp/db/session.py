from __future__ import annotations

from sqlalchemy import Engine
from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy.orm import sessionmaker

from repo_dependency_context_mcp.config import Settings


def create_engine(settings: Settings | None = None) -> Engine:
    active_settings = settings or Settings()
    return sqlalchemy_create_engine(active_settings.database_url, future=True)


def create_session_factory(settings: Settings | None = None) -> sessionmaker:
    engine = create_engine(settings)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)
