from sqlalchemy.orm import DeclarativeBase

from repo_dependency_context_mcp.db.meta import metadata


class Base(DeclarativeBase):
    metadata = metadata
