from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from repo_dependency_context_mcp.db.models import SyncCursor, SyncRun


class SyncStateService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_cursor(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        source_kind: str,
        scope_key: str,
    ) -> SyncCursor | None:
        return self.session.execute(
            select(SyncCursor).where(
                SyncCursor.tenant_id == tenant_id,
                SyncCursor.repo_id == repo_id,
                SyncCursor.source_kind == source_kind,
                SyncCursor.scope_key == scope_key,
            )
        ).scalar_one_or_none()

    def upsert_cursor(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        source_kind: str,
        scope_key: str,
        cursor_kind: str,
        cursor_value: str | None,
    ) -> SyncCursor:
        cursor = self.get_cursor(
            tenant_id=tenant_id,
            repo_id=repo_id,
            source_kind=source_kind,
            scope_key=scope_key,
        )
        if cursor is None:
            cursor = SyncCursor(
                tenant_id=tenant_id,
                repo_id=repo_id,
                source_kind=source_kind,
                scope_key=scope_key,
                cursor_kind=cursor_kind,
                cursor_value=cursor_value,
            )
            self.session.add(cursor)
        else:
            cursor.cursor_kind = cursor_kind
            cursor.cursor_value = cursor_value
        self.session.flush()
        return cursor

    def start_run(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        source_kind: str,
        scope_key: str,
        cursor_kind: str,
    ) -> SyncRun:
        cursor = self.get_cursor(
            tenant_id=tenant_id,
            repo_id=repo_id,
            source_kind=source_kind,
            scope_key=scope_key,
        )
        if cursor is None:
            cursor = self.upsert_cursor(
                tenant_id=tenant_id,
                repo_id=repo_id,
                source_kind=source_kind,
                scope_key=scope_key,
                cursor_kind=cursor_kind,
                cursor_value=None,
            )

        run = SyncRun(
            tenant_id=tenant_id,
            repo_id=repo_id,
            source_kind=source_kind,
            scope_key=scope_key,
            status="running",
            started_at=_utcnow(),
            cursor_before=cursor.cursor_value,
        )
        self.session.add(run)
        self.session.commit()
        return run

    def mark_success(
        self,
        run: SyncRun,
        cursor_after: str | None,
        items_seen: int,
        items_written: int,
    ) -> SyncRun:
        managed_run = self.session.get(SyncRun, run.id)
        if managed_run is None:
            raise ValueError("sync run not found")

        cursor = self.get_cursor(
            tenant_id=managed_run.tenant_id,
            repo_id=managed_run.repo_id,
            source_kind=managed_run.source_kind,
            scope_key=managed_run.scope_key,
        )
        if cursor is None:
            raise ValueError("sync cursor not found")

        now = _utcnow()
        managed_run.status = "completed"
        managed_run.finished_at = now
        managed_run.items_seen = items_seen
        managed_run.items_written = items_written
        managed_run.cursor_after = cursor_after
        managed_run.error = None

        cursor.cursor_value = cursor_after
        cursor.last_synced_at = now
        cursor.last_success_at = now
        cursor.last_error = None

        self.session.commit()
        return managed_run

    def mark_failure(self, run: SyncRun, error: str) -> SyncRun:
        managed_run = self.session.get(SyncRun, run.id)
        if managed_run is None:
            raise ValueError("sync run not found")

        cursor = self.get_cursor(
            tenant_id=managed_run.tenant_id,
            repo_id=managed_run.repo_id,
            source_kind=managed_run.source_kind,
            scope_key=managed_run.scope_key,
        )
        if cursor is None:
            raise ValueError("sync cursor not found")

        now = _utcnow()
        managed_run.status = "failed"
        managed_run.finished_at = now
        managed_run.error = error
        managed_run.cursor_after = cursor.cursor_value

        cursor.last_synced_at = now
        cursor.last_failure_at = now
        cursor.last_error = error

        self.session.commit()
        return managed_run


def _utcnow() -> datetime:
    return datetime.now(UTC)
