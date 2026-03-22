from __future__ import annotations

import os
from dataclasses import dataclass


def _read_csv_env(name: str, default: str) -> list[str]:
    raw_value = os.getenv(name, default)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    app_name: str = "repo-dependency-context-mcp"
    env: str = "development"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/rdcmcp"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    default_top_k: int = 5
    vendor_official_domains: list[str] | None = None
    embedding_provider: str = "local"
    embedding_dimension: int = 1536
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    rerank_provider: str = "local"
    openai_rerank_model: str = "gpt-5-mini"

    def __post_init__(self) -> None:
        self.app_name = os.getenv("RDCMCP_APP_NAME", self.app_name)
        self.env = os.getenv("RDCMCP_ENV", self.env)
        self.database_url = os.getenv("RDCMCP_DATABASE_URL", self.database_url)
        self.redis_url = os.getenv("RDCMCP_REDIS_URL", self.redis_url)
        self.log_level = os.getenv("RDCMCP_LOG_LEVEL", self.log_level)
        self.default_top_k = int(os.getenv("RDCMCP_DEFAULT_TOP_K", str(self.default_top_k)))
        self.embedding_provider = os.getenv("RDCMCP_EMBEDDING_PROVIDER", self.embedding_provider)
        self.embedding_dimension = int(os.getenv("RDCMCP_EMBEDDING_DIMENSION", str(self.embedding_dimension)))
        self.openai_api_key = os.getenv("RDCMCP_OPENAI_API_KEY", self.openai_api_key)
        self.openai_embedding_model = os.getenv("RDCMCP_OPENAI_EMBEDDING_MODEL", self.openai_embedding_model)
        self.rerank_provider = os.getenv("RDCMCP_RERANK_PROVIDER", self.rerank_provider)
        self.openai_rerank_model = os.getenv("RDCMCP_OPENAI_RERANK_MODEL", self.openai_rerank_model)
        self.vendor_official_domains = _read_csv_env(
            "RDCMCP_VENDOR_OFFICIAL_DOMAINS",
            "docs.python.org,fastapi.tiangolo.com,docs.sqlalchemy.org",
        )

    def validate(self) -> None:
        if self.embedding_provider == "openai" and not self.openai_api_key:
            raise ValueError("openai api key is required when RDCMCP_EMBEDDING_PROVIDER=openai")
        if self.rerank_provider == "openai" and not self.openai_api_key:
            raise ValueError("openai api key is required when RDCMCP_RERANK_PROVIDER=openai")
