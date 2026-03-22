from __future__ import annotations

import uuid
from pathlib import Path

from repo_dependency_context_mcp.api.deps import get_db_session
from repo_dependency_context_mcp.services.dependencies.vendor_docs import (
    VendorDocDiscoveryRequest,
    VendorDocFetchRequest,
    VendorDocIngestService,
)
from repo_dependency_context_mcp.services.eval.runner import EvalRunnerService
from repo_dependency_context_mcp.services.ingest.github_metadata import GitHubMetadataIngestService
from repo_dependency_context_mcp.services.ingest.sync_state import SyncStateService
from repo_dependency_context_mcp.workers.celery_app import celery_app


@celery_app.task(name="rdcmcp.ingest_github_metadata")
def ingest_github_metadata_task(
    tenant_id: str,
    repo_id: str,
    owner: str,
    repo_name: str,
    acl_scope: dict,
    base_url: str | None = None,
) -> dict:
    with get_db_session() as session:
        written = GitHubMetadataIngestService(
            session,
            base_url=base_url or "https://api.github.com",
        ).ingest_repo_changes(
            tenant_id=uuid.UUID(tenant_id),
            repo_id=uuid.UUID(repo_id),
            owner=owner,
            repo_name=repo_name,
            acl_scope=acl_scope,
        )
        sync_state = SyncStateService(session)
        scope_key = f"{owner}/{repo_name}:pulls"
        latest_run = sync_state.get_latest_run(
            tenant_id=uuid.UUID(tenant_id),
            repo_id=uuid.UUID(repo_id),
            source_kind="github_prs",
            scope_key=scope_key,
        )
        cursor = sync_state.get_cursor(
            tenant_id=uuid.UUID(tenant_id),
            repo_id=uuid.UUID(repo_id),
            source_kind="github_prs",
            scope_key=scope_key,
        )
        return {
            "items_written": written,
            "sync": {
                "source_kind": "github_prs",
                "scope_key": scope_key,
                "status": latest_run.status if latest_run else None,
                "cursor_value": cursor.cursor_value if cursor else None,
            },
        }


@celery_app.task(name="rdcmcp.fetch_vendor_docs")
def fetch_vendor_docs_task(
    package_name: str,
    ecosystem: str,
    official_domains: dict[str, list[str]],
    requests: list[dict],
) -> dict:
    with get_db_session() as session:
        typed_requests = [VendorDocFetchRequest(**item) for item in requests]
        written = VendorDocIngestService(
            session,
            official_domains=official_domains,
        ).fetch_and_ingest(
            package_name=package_name,
            ecosystem=ecosystem,
            requests=typed_requests,
        )
        sync_state = SyncStateService(session)
        scope_key = f"{package_name}:{ecosystem}"
        tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        latest_run = sync_state.get_latest_run(
            tenant_id=tenant_id,
            repo_id=None,
            source_kind="vendor_docs",
            scope_key=scope_key,
        )
        cursor = sync_state.get_cursor(
            tenant_id=tenant_id,
            repo_id=None,
            source_kind="vendor_docs",
            scope_key=scope_key,
        )
        return {
            "items_written": written,
            "sync": {
                "source_kind": "vendor_docs",
                "scope_key": scope_key,
                "status": latest_run.status if latest_run else None,
                "cursor_value": cursor.cursor_value if cursor else None,
            },
        }


@celery_app.task(name="rdcmcp.discover_vendor_docs")
def discover_vendor_docs_task(
    package_name: str,
    ecosystem: str,
    official_domains: dict[str, list[str]],
    requests: list[dict],
) -> dict:
    with get_db_session() as session:
        typed_requests = [VendorDocDiscoveryRequest(**item) for item in requests]
        written = VendorDocIngestService(
            session,
            official_domains=official_domains,
        ).discover_and_ingest(
            package_name=package_name,
            ecosystem=ecosystem,
            requests=typed_requests,
        )
        sync_state = SyncStateService(session)
        scope_key = f"{package_name}:{ecosystem}"
        tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
        latest_run = sync_state.get_latest_run(
            tenant_id=tenant_id,
            repo_id=None,
            source_kind="vendor_docs",
            scope_key=scope_key,
        )
        cursor = sync_state.get_cursor(
            tenant_id=tenant_id,
            repo_id=None,
            source_kind="vendor_docs",
            scope_key=scope_key,
        )
        return {
            "items_written": written,
            "sync": {
                "source_kind": "vendor_docs",
                "scope_key": scope_key,
                "status": latest_run.status if latest_run else None,
                "cursor_value": cursor.cursor_value if cursor else None,
            },
        }


@celery_app.task(name="rdcmcp.run_eval")
def run_eval_task(dataset_path: str) -> dict:
    with get_db_session() as session:
        return EvalRunnerService(session).run_from_yaml(Path(dataset_path))
