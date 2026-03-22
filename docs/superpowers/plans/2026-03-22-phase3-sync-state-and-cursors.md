# Phase 3 Sync State And Cursors Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable sync cursors and run history for GitHub metadata and vendor docs ingestion so repeated syncs can resume safely and observably.

**Architecture:** Introduce additive `sync_cursors` and `sync_runs` tables plus a small sync-state service that GitHub and vendor-doc ingest flows call into. Keep cursor advancement success-only, reuse existing idempotent ingest behavior, and add focused CLI/task-safe tests around reruns and failures.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.x, Alembic, FastAPI service layer, pytest

---

## File Map

### New files

- `src/repo_dependency_context_mcp/db/models/sync_state.py`
  - ORM models for `SyncCursor` and `SyncRun`
- `src/repo_dependency_context_mcp/services/ingest/sync_state.py`
  - cursor/run lifecycle service
- `migrations/versions/<timestamp>_add_sync_state_tables.py`
  - additive schema migration
- `tests/unit/test_sync_state_models.py`
  - model-level coverage for uniqueness/basic fields
- `tests/integration/test_sync_state_service.py`
  - service behavior for start/success/failure transitions

### Modified files

- `src/repo_dependency_context_mcp/db/models/__init__.py`
  - export new sync models
- `src/repo_dependency_context_mcp/services/ingest/github_metadata.py`
  - read/write GitHub sync cursors and sync runs
- `src/repo_dependency_context_mcp/services/dependencies/vendor_docs.py`
  - write vendor docs sync runs/cursor state
- `src/repo_dependency_context_mcp/workers/tasks/jobs.py`
  - surface sync metadata in task results if needed
- `src/repo_dependency_context_mcp/cli/main.py`
  - ensure current sync commands use the new stateful behavior
- `tests/integration/test_github_metadata_ingest.py`
  - add incremental sync assertions
- `tests/integration/test_vendor_doc_fetcher.py`
  - add vendor-doc sync-state assertions
- `tests/integration/test_job_flows.py`
  - verify task entrypoints still work with sync-state wiring

## Chunk 1: Schema And Sync-State Service

### Task 1: Add failing model tests for sync state

**Files:**
- Create: `tests/unit/test_sync_state_models.py`
- Modify: none
- Test: `tests/unit/test_sync_state_models.py`

- [ ] **Step 1: Write the failing test**

```python
def test_sync_cursor_can_be_created(db_session: Session) -> None:
    cursor = SyncCursor(
        tenant_id=tenant_id,
        repo_id=repo_id,
        source_kind="github_prs",
        scope_key="owner/repo:pulls",
        cursor_kind="updated_at",
        cursor_value="2026-03-22T00:00:00Z",
    )
    db_session.add(cursor)
    db_session.commit()
    assert cursor.id is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_sync_state_models.py -v`
Expected: FAIL because `SyncCursor`/`SyncRun` do not exist yet

- [ ] **Step 3: Write minimal implementation**

- create `sync_state.py` ORM models
- export them from `db/models/__init__.py`

- [ ] **Step 4: Run test to verify it still fails on missing tables**

Run: `pytest tests/unit/test_sync_state_models.py -v`
Expected: FAIL with missing table/migration issue

- [ ] **Step 5: Commit**

```bash
git add tests/unit/test_sync_state_models.py src/repo_dependency_context_mcp/db/models/sync_state.py src/repo_dependency_context_mcp/db/models/__init__.py
git commit -m "test(sync): add sync state model coverage"
```

### Task 2: Add Alembic migration for sync tables

**Files:**
- Create: `migrations/versions/<timestamp>_add_sync_state_tables.py`
- Modify: `src/repo_dependency_context_mcp/db/models/sync_state.py`
- Test: `tests/unit/test_sync_state_models.py`

- [ ] **Step 1: Write uniqueness assertion**

```python
def test_sync_cursor_scope_is_unique(db_session: Session) -> None:
    db_session.add(first_cursor)
    db_session.commit()
    db_session.add(duplicate_cursor)
    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_sync_state_models.py::test_sync_cursor_scope_is_unique -v`
Expected: FAIL before migration

- [ ] **Step 3: Write migration**

- create `sync_cursors`
- create `sync_runs`
- add uniqueness/indexes

- [ ] **Step 4: Apply migration and rerun tests**

Run:
- `python -m alembic upgrade head`
- `pytest tests/unit/test_sync_state_models.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migrations/versions src/repo_dependency_context_mcp/db/models/sync_state.py tests/unit/test_sync_state_models.py
git commit -m "feat(sync): add sync cursor and run tables"
```

### Task 3: Add sync-state service with success/failure semantics

**Files:**
- Create: `src/repo_dependency_context_mcp/services/ingest/sync_state.py`
- Create: `tests/integration/test_sync_state_service.py`
- Modify: none
- Test: `tests/integration/test_sync_state_service.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_mark_success_advances_cursor(db_session: Session) -> None:
    service = SyncStateService(db_session)
    run = service.start_run(...)
    service.mark_success(run, cursor_after="2026-03-22T10:00:00Z", items_seen=3, items_written=2)
    cursor = service.get_cursor(...)
    assert cursor.cursor_value == "2026-03-22T10:00:00Z"

def test_mark_failure_preserves_previous_cursor(db_session: Session) -> None:
    service = SyncStateService(db_session)
    service.seed_cursor(..., cursor_value="2026-03-22T09:00:00Z")
    run = service.start_run(...)
    service.mark_failure(run, error="boom")
    cursor = service.get_cursor(...)
    assert cursor.cursor_value == "2026-03-22T09:00:00Z"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_sync_state_service.py -v`
Expected: FAIL because service does not exist

- [ ] **Step 3: Write minimal implementation**

- implement:
  - `get_cursor(...)`
  - `start_run(...)`
  - `mark_success(...)`
  - `mark_failure(...)`

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_sync_state_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/repo_dependency_context_mcp/services/ingest/sync_state.py tests/integration/test_sync_state_service.py
git commit -m "feat(sync): add sync state service"
```

## Chunk 2: GitHub Metadata Incremental Sync

### Task 4: Add failing GitHub incremental sync tests

**Files:**
- Modify: `tests/integration/test_github_metadata_ingest.py`
- Modify: `src/repo_dependency_context_mcp/services/ingest/github_metadata.py`
- Test: `tests/integration/test_github_metadata_ingest.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_github_sync_advances_pr_cursor_after_success(...) -> None:
    service.ingest_remote(...)
    cursor = lookup_cursor("github_prs", "owner/repo:pulls")
    assert cursor.cursor_value == "2026-03-22T10:00:00Z"

def test_github_sync_second_run_skips_old_items(...) -> None:
    service.ingest_remote(...)
    service.ingest_remote(...)
    assert count_change_documents(db_session) == expected_once
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_github_metadata_ingest.py -v`
Expected: FAIL because no cursor state is used yet

- [ ] **Step 3: Implement incremental cursor wiring**

- use separate cursors for:
  - `github_prs`
  - `github_issues`
  - `github_commits`
- create `sync_runs`
- advance cursor only on success

- [ ] **Step 4: Run tests**

Run: `pytest tests/integration/test_github_metadata_ingest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/repo_dependency_context_mcp/services/ingest/github_metadata.py tests/integration/test_github_metadata_ingest.py
git commit -m "feat(sync): add github metadata cursors"
```

### Task 5: Add failure-path GitHub sync test

**Files:**
- Modify: `tests/integration/test_github_metadata_ingest.py`
- Modify: `src/repo_dependency_context_mcp/services/ingest/github_metadata.py`
- Test: `tests/integration/test_github_metadata_ingest.py`

- [ ] **Step 1: Write the failing test**

```python
def test_github_sync_failure_does_not_advance_cursor(...) -> None:
    seed_cursor(...)
    failing_service.ingest_remote(...)
    cursor = lookup_cursor("github_prs", "owner/repo:pulls")
    assert cursor.cursor_value == previous_value
    assert latest_sync_run.status == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_github_metadata_ingest.py::test_github_sync_failure_does_not_advance_cursor -v`
Expected: FAIL

- [ ] **Step 3: Implement failure handling**

- ensure exception paths call `mark_failure(...)`
- preserve cursor row

- [ ] **Step 4: Run tests**

Run: `pytest tests/integration/test_github_metadata_ingest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/repo_dependency_context_mcp/services/ingest/github_metadata.py tests/integration/test_github_metadata_ingest.py
git commit -m "fix(sync): preserve github cursor on failure"
```

## Chunk 3: Vendor Docs Sync State

### Task 6: Add failing vendor-doc sync-state tests

**Files:**
- Modify: `tests/integration/test_vendor_doc_fetcher.py`
- Modify: `src/repo_dependency_context_mcp/services/dependencies/vendor_docs.py`
- Test: `tests/integration/test_vendor_doc_fetcher.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_vendor_doc_fetch_records_sync_run(...) -> None:
    service.fetch_and_ingest(...)
    run = latest_sync_run("vendor_docs", "fastapi:python")
    assert run.status == "completed"

def test_vendor_doc_failure_records_failure_without_advancing_cursor(...) -> None:
    seed_cursor(...)
    failing_fetch(...)
    cursor = lookup_cursor("vendor_docs", "fastapi:python")
    assert cursor.cursor_value == previous_value
    assert latest_sync_run.status == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_vendor_doc_fetcher.py -v`
Expected: FAIL because vendor-doc sync state is not persisted yet

- [ ] **Step 3: Implement sync-state wiring**

- create sync run per package/ecosystem sync
- mark success/failure
- update vendor-doc cursor metadata after success

- [ ] **Step 4: Run tests**

Run: `pytest tests/integration/test_vendor_doc_fetcher.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/repo_dependency_context_mcp/services/dependencies/vendor_docs.py tests/integration/test_vendor_doc_fetcher.py
git commit -m "feat(sync): add vendor docs sync state"
```

### Task 7: Keep CLI/task flows green

**Files:**
- Modify: `tests/integration/test_job_flows.py`
- Modify: `src/repo_dependency_context_mcp/workers/tasks/jobs.py`
- Modify: `src/repo_dependency_context_mcp/cli/main.py`
- Test: `tests/integration/test_job_flows.py`

- [ ] **Step 1: Write the failing assertions**

```python
def test_github_job_flow_records_sync_state(...) -> None:
    result = ingest_github_metadata_task(...)
    assert result["status"] == "completed"

def test_vendor_discover_job_flow_records_sync_state(...) -> None:
    result = discover_vendor_docs_task(...)
    assert result["status"] == "completed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_job_flows.py -v`
Expected: FAIL if task return values or wiring do not match new sync-state behavior

- [ ] **Step 3: Implement minimal task/CLI updates**

- preserve current command surface
- ensure new stateful services are invoked cleanly

- [ ] **Step 4: Run tests**

Run: `pytest tests/integration/test_job_flows.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/repo_dependency_context_mcp/workers/tasks/jobs.py src/repo_dependency_context_mcp/cli/main.py tests/integration/test_job_flows.py
git commit -m "chore(sync): keep job flows aligned with cursor state"
```

## Chunk 4: Final Verification And Docs

### Task 8: Run focused verification

**Files:**
- Modify: none, unless fixes are needed
- Test:
  - `tests/unit/test_sync_state_models.py`
  - `tests/integration/test_sync_state_service.py`
  - `tests/integration/test_github_metadata_ingest.py`
  - `tests/integration/test_vendor_doc_fetcher.py`
  - `tests/integration/test_job_flows.py`

- [ ] **Step 1: Run focused tests**

Run:

```bash
pytest tests/unit/test_sync_state_models.py tests/integration/test_sync_state_service.py tests/integration/test_github_metadata_ingest.py tests/integration/test_vendor_doc_fetcher.py tests/integration/test_job_flows.py -v
```

Expected: PASS

- [ ] **Step 2: Run full suite**

Run:

```bash
pytest
```

Expected: PASS

- [ ] **Step 3: Run quality checks on touched files**

Run:

```bash
ruff check src tests --select F,I
```

Expected: PASS

- [ ] **Step 4: Commit final cleanups if needed**

```bash
git add -A
git commit -m "test(sync): finalize phase 3 verification"
```

## Execution Notes

- Keep the first implementation slice limited to GitHub and vendor docs
- Do not attempt repo-ingest cursors in the same chunk
- Prefer additive schema and service wiring over refactoring current ingest flows
- Reuse existing idempotent document/chunk behavior; cursor logic should decide fetch range, not rewrite ingest semantics

Plan complete and saved to `docs/superpowers/plans/2026-03-22-phase3-sync-state-and-cursors.md`. Ready to execute?
