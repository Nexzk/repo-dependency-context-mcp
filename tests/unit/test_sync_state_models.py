from __future__ import annotations

from repo_dependency_context_mcp.db.base import Base
from repo_dependency_context_mcp.db.models import SyncCursor, SyncRun  # noqa: F401


def test_sync_state_tables_are_registered() -> None:
    expected_tables = {
        "sync_cursors",
        "sync_runs",
    }

    assert expected_tables.issubset(Base.metadata.tables.keys())


def test_sync_cursor_scope_is_unique() -> None:
    table = Base.metadata.tables["sync_cursors"]

    assert "cursor_kind" in table.c
    assert "cursor_value" in table.c
    assert any(
        constraint.columns.keys() == ["tenant_id", "repo_id", "source_kind", "scope_key"]
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    )


def test_sync_run_tracks_before_after_and_status() -> None:
    table = Base.metadata.tables["sync_runs"]

    assert "status" in table.c
    assert "cursor_before" in table.c
    assert "cursor_after" in table.c
    assert "items_seen" in table.c
    assert "items_written" in table.c
