from __future__ import annotations

import uuid

from repo_dependency_context_mcp.db.models import Repo, Tenant
from repo_dependency_context_mcp.services.ingest.sync_state import SyncStateService


def test_mark_success_advances_cursor(db_session) -> None:
    tenant_id, repo_id = _create_repo_scope(db_session)
    service = SyncStateService(db_session)

    run = service.start_run(
        tenant_id=tenant_id,
        repo_id=repo_id,
        source_kind="github_prs",
        scope_key="owner/repo:pulls",
        cursor_kind="updated_at",
    )
    service.mark_success(
        run=run,
        cursor_after="2026-03-22T10:00:00Z",
        items_seen=3,
        items_written=2,
    )

    cursor = service.get_cursor(
        tenant_id=tenant_id,
        repo_id=repo_id,
        source_kind="github_prs",
        scope_key="owner/repo:pulls",
    )
    assert cursor is not None
    assert cursor.cursor_value == "2026-03-22T10:00:00Z"
    assert cursor.last_success_at is not None


def test_mark_failure_preserves_previous_cursor(db_session) -> None:
    tenant_id, repo_id = _create_repo_scope(db_session)
    service = SyncStateService(db_session)

    service.upsert_cursor(
        tenant_id=tenant_id,
        repo_id=repo_id,
        source_kind="github_prs",
        scope_key="owner/repo:pulls",
        cursor_kind="updated_at",
        cursor_value="2026-03-22T09:00:00Z",
    )
    run = service.start_run(
        tenant_id=tenant_id,
        repo_id=repo_id,
        source_kind="github_prs",
        scope_key="owner/repo:pulls",
        cursor_kind="updated_at",
    )
    service.mark_failure(run=run, error="boom")

    cursor = service.get_cursor(
        tenant_id=tenant_id,
        repo_id=repo_id,
        source_kind="github_prs",
        scope_key="owner/repo:pulls",
    )
    latest_run = db_session.get(type(run), run.id)

    assert cursor is not None
    assert cursor.cursor_value == "2026-03-22T09:00:00Z"
    assert cursor.last_failure_at is not None
    assert cursor.last_error == "boom"
    assert latest_run is not None
    assert latest_run.status == "failed"
    assert latest_run.cursor_before == "2026-03-22T09:00:00Z"


def _create_repo_scope(db_session) -> tuple[uuid.UUID, uuid.UUID]:
    tenant = Tenant(name="Tenant Sync State", slug=f"tenant-sync-state-{uuid.uuid4().hex[:8]}")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="repo-sync-state",
        provider="local",
        external_id=f"repo-sync-state-{uuid.uuid4()}",
        default_branch="main",
        acl_scope={"visibility": "private"},
    )
    db_session.add(repo)
    db_session.commit()

    return tenant.id, repo.id
