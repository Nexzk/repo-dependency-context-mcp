from __future__ import annotations

from celery import Celery

from repo_dependency_context_mcp.config import Settings


def create_celery_app(settings: Settings | None = None) -> Celery:
    active_settings = settings or Settings()
    return Celery(
        "repo_dependency_context_mcp",
        broker=active_settings.redis_url,
        backend=active_settings.redis_url,
    )


celery_app = create_celery_app()
