# Phase 3 Sync State And Cursors Design

## Goal

Add durable incremental sync state for external metadata ingestion so repeated runs can resume from a known checkpoint instead of re-scanning everything.

## Scope

Phase 3 starts with GitHub metadata sync and leaves local repo ingest as a later extension. The immediate target is to persist cursor/checkpoint state for:

- pull requests
- issues
- commits
- vendor docs discovery/fetch

The design keeps the current product scope unchanged. It only improves how existing sync jobs decide what to fetch next, how they record success/failure, and how operators inspect the last known sync state.

## Non-Goals

- no new external connectors beyond existing GitHub-style ingest and vendor docs fetch
- no graph-based related change model
- no scheduler/orchestrator redesign
- no broad refactor of `ingest_jobs`

## Problem

The current system has idempotent ingest behavior and basic job status, but it still lacks a durable sync checkpoint model. That creates three operational gaps:

1. repeated GitHub metadata syncs cannot cheaply resume from a prior successful point
2. failures do not clearly distinguish "last attempted" from "last successful" sync positions
3. vendor docs sync cannot record a stable per-package/per-source checkpoint for later re-runs

## Recommended Approach

Use two new tables:

- `sync_cursors`
- `sync_runs`

This keeps the current `ingest_jobs` semantics intact while giving external sync flows their own checkpoint and run-history model.

### Why this approach

- simpler than creating one table per sync source
- cleaner than overloading `ingest_jobs` with mixed job history and checkpoint state
- easy to query in API/CLI/ops tooling
- supports future expansion to more source kinds without schema churn

## Data Model

### `sync_cursors`

Purpose: store the latest known checkpoint for one sync stream.

Suggested uniqueness:

- `(tenant_id, repo_id, source_kind, scope_key)`

Fields:

- `id`
- `tenant_id`
- `repo_id`
- `source_kind`
- `scope_key`
- `cursor_kind`
- `cursor_value`
- `last_synced_at`
- `last_success_at`
- `last_failure_at`
- `last_error`
- `created_at`
- `updated_at`

Definitions:

- `source_kind`
  - examples: `github_prs`, `github_issues`, `github_commits`, `vendor_docs`
- `scope_key`
  - stable sub-scope within a source kind
  - examples:
    - `owner/repo:pulls`
    - `owner/repo:issues`
    - `owner/repo:commits`
    - `fastapi:python`
- `cursor_kind`
  - examples: `updated_at`, `committed_at`, `index_url`, `opaque`
- `cursor_value`
  - serialized string checkpoint
  - examples: ISO timestamp, SHA, version, URL token

### `sync_runs`

Purpose: record each sync attempt separately from the durable cursor row.

Fields:

- `id`
- `tenant_id`
- `repo_id`
- `source_kind`
- `scope_key`
- `status`
- `started_at`
- `finished_at`
- `items_seen`
- `items_written`
- `cursor_before`
- `cursor_after`
- `error`
- `metadata_json`

Status values:

- `running`
- `completed`
- `failed`

## Source-Specific Cursor Strategy

### GitHub pull requests

- source kind: `github_prs`
- scope key: `<owner>/<repo>:pulls`
- cursor kind: `updated_at`
- cursor value: latest successful PR `updated_at`

Behavior:

- fetch PRs ordered by update time
- process only items newer than the stored cursor
- on success, advance to the max processed `updated_at`
- on failure, keep `cursor_value` unchanged and record `last_failure_at`/`last_error`

### GitHub issues

- source kind: `github_issues`
- scope key: `<owner>/<repo>:issues`
- cursor kind: `updated_at`
- cursor value: latest successful issue `updated_at`

Behavior mirrors PR sync.

### GitHub commits

- source kind: `github_commits`
- scope key: `<owner>/<repo>:commits`
- cursor kind: `committed_at`
- cursor value: latest successful commit timestamp

Reasoning:

- timestamp cursor is simpler than branch-specific SHA cursors for the current MVP
- acceptable as a first incremental model
- if later needed, this can evolve to branch+SHA without breaking the table structure

### Vendor docs

- source kind: `vendor_docs`
- scope key: `<package_name>:<ecosystem>`
- cursor kind: `index_url`
- cursor value: a stable token or serialized summary of the last successful sync target

Initial Phase 3 behavior:

- record each sync run and last success/failure per package/ecosystem
- use the cursor row primarily as durable sync state rather than aggressive incremental crawling logic

This keeps vendor docs support honest: we gain state visibility first, then smarter deltas later.

## Service Changes

### New sync-state service

Add a focused service responsible for:

- loading current cursor for a sync stream
- creating `sync_runs`
- marking run success/failure
- updating `sync_cursors` only after successful completion

This should be a small, reusable unit that other ingest services call into.

### GitHub metadata ingest integration

The GitHub ingest flow should:

1. resolve the cursor row for each resource type
2. create a `sync_run`
3. fetch items newer than `cursor_before`
4. reuse existing idempotent ingest logic for writes
5. update run counters
6. advance the cursor only on success

### Vendor docs integration

Vendor doc fetch/discovery should:

1. create a sync run for the package/ecosystem scope
2. execute the current fetch/discovery logic
3. record counts and success/failure
4. update the cursor row with last successful sync metadata

## ACL And Isolation

All sync state must remain tenant/repo scoped.

Rules:

- every row includes `tenant_id`
- repo-scoped sync rows include `repo_id`
- queries always filter by tenant and repo
- no cursor row can be shared across repos even if the upstream package/repository names match

## Failure Semantics

Success and checkpoint advancement must be coupled.

Rules:

- never advance `cursor_value` on partial failure
- always write a failed `sync_run` when a sync attempt aborts
- preserve the previous successful cursor after any failed attempt
- store a human-readable `last_error`

## Testing Strategy

### Database/model tests

- cursor uniqueness by `(tenant_id, repo_id, source_kind, scope_key)`
- run creation and state transitions

### GitHub sync tests

- first sync creates rows and advances cursor
- second sync with same data writes nothing new
- newer upstream item advances cursor
- failed sync does not advance cursor
- tenant/repo isolation holds

### Vendor docs sync tests

- sync run rows are recorded for fetch/discovery
- repeated runs update last success without duplicating docs
- failure records `last_failure_at` and preserves prior cursor

## Migration Strategy

Single additive migration:

- create `sync_cursors`
- create `sync_runs`
- add indexes and uniqueness constraint

No data backfill is required for Phase 3. Existing repositories simply start with no cursor row and perform a first full sync.

## Operational Visibility

Minimum observability additions:

- expose sync run summaries in existing ops/debug surfaces later
- CLI/task logs should include `source_kind`, `scope_key`, `cursor_before`, `cursor_after`

This is enough to debug whether a sync really resumed incrementally.

## Risks

### Timestamp cursor ambiguity

If upstream APIs return equal timestamps or out-of-order updates, a pure timestamp cursor can miss edge items.

Mitigation:

- normalize to max timestamp seen in the batch
- optionally include a small overlap window in the fetch layer later
- keep idempotent writes so overlap is safe

### Over-promising vendor-doc incrementality

Vendor docs are not yet a crawler with stable change tokens.

Mitigation:

- Phase 3 records durable run state first
- later work can add smarter content-level delta logic without redesigning the schema

## Exit Criteria

Phase 3 first slice is complete when:

- GitHub metadata sync uses durable cursor rows
- successful runs advance cursors
- failed runs do not advance cursors
- vendor docs sync records durable run history and checkpoint state
- tests prove idempotent reruns and failure handling
