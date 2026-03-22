from __future__ import annotations

import uuid
from pathlib import Path

from repo_dependency_context_mcp.api.deps import get_db_session
from repo_dependency_context_mcp.services.dependencies.vendor_docs import (
    VendorDocFetchRequest,
    VendorDocIngestService,
)
from repo_dependency_context_mcp.services.eval.runner import EvalRunnerService
from repo_dependency_context_mcp.services.ingest.github_metadata import GitHubMetadataIngestService
from repo_dependency_context_mcp.workers.celery_app import celery_app


@celery_app.task(name="rdcmcp.ingest_github_metadata")
def ingest_github_metadata_task(
    tenant_id: str,
    repo_id: str,
    owner: str,
    repo_name: str,
    acl_scope: dict,
    base_url: str | None = None,
) -> int:
    with get_db_session() as session:
        return GitHubMetadataIngestService(session, base_url=base_url or "https://api.github.com").ingest_repo_changes(
            tenant_id=uuid.UUID(tenant_id),
            repo_id=uuid.UUID(repo_id),
            owner=owner,
            repo_name=repo_name,
            acl_scope=acl_scope,
        )


@celery_app.task(name="rdcmcp.fetch_vendor_docs")
def fetch_vendor_docs_task(
    package_name: str,
    ecosystem: str,
    official_domains: dict[str, list[str]],
    requests: list[dict],
) -> int:
    with get_db_session() as session:
        typed_requests = [VendorDocFetchRequest(**item) for item in requests]
        return VendorDocIngestService(session, official_domains=official_domains).fetch_and_ingest(
            package_name=package_name,
            ecosystem=ecosystem,
            requests=typed_requests,
        )


@celery_app.task(name="rdcmcp.run_eval")
def run_eval_task(dataset_path: str) -> dict:
    with get_db_session() as session:
        return EvalRunnerService(session).run_from_yaml(Path(dataset_path))
