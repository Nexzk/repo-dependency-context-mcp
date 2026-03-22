# Phase 2 Plan

Branch: `phase2-hardening-and-sync`

## Goal

Turn the MVP into a more durable internal system by improving sync correctness, retrieval quality, and operational safety without expanding the product scope.

## Priority Order

1. incremental sync and job state
2. stronger related-change association
3. vendor docs discovery and batch sync
4. quality gate expansion

## Workstream 1: Incremental Sync and Job State

Status: completed on branch `phase2-hardening-and-sync`

### Scope

- persist sync cursors/checkpoints for:
  - GitHub PRs
  - issues
  - commits
  - vendor docs fetch jobs
- track job start/end/error state more explicitly
- support safe re-run without duplicating documents and chunks

### Deliverables

- schema additions for sync state and job metadata
- service-layer idempotent upsert behavior
- CLI/task commands that support re-sync
- tests proving repeated syncs do not duplicate data

### Exit Criteria

- rerunning GitHub metadata ingest is idempotent
- rerunning vendor doc fetch is idempotent
- ingest job rows show meaningful status transitions

## Workstream 2: Stronger Related Changes

Status: completed on branch `phase2-hardening-and-sync`

### Scope

- improve `get_related_changes` beyond token matching
- connect source chunks to:
  - file paths
  - symbol paths
  - commit refs
  - PR refs
- prefer recent merged PRs and commits for the same path/symbol

### Deliverables

- richer metadata on change chunks
- scoring rules for path and symbol affinity
- tests covering:
  - exact path match
  - symbol-only match
  - multiple related changes with ranking

### Exit Criteria

- PR / commit / issue ranking is deterministic
- exact path or symbol matches outrank weak lexical matches

## Workstream 3: Vendor Docs Discovery and Batch Sync

Status: completed on branch `phase2-hardening-and-sync`

### Scope

- move from single-page fetch to controlled multi-page discovery
- keep whitelist enforcement strict
- add package-specific seed URLs and document types
- batch ingest docs/changelog/migration pages per dependency

### Deliverables

- discovery configuration format
- fetch queue generation
- deduplicated vendor doc ingest
- tests using local HTTP fixtures for multi-page sync

### Exit Criteria

- one command can ingest multiple whitelisted vendor pages
- duplicate pages are not reinserted
- non-whitelisted links are ignored

## Workstream 4: Quality Gate Expansion

Status: partially completed on branch `phase2-hardening-and-sync`

### Scope

- widen Ruff coverage beyond `F,I`
- widen MyPy coverage incrementally
- optionally add smoke execution to CI

### Deliverables

- staged lint/type targets
- updated CI steps
- documented quality policy for what is enforced and why

### Exit Criteria

- CI remains high signal
- new enforcement does not create permanent flaky failures

Implemented so far:

- focused MyPy expanded from provider-only coverage to include:
  - `services/ingest/change_metadata.py`
  - `services/ingest/github_metadata.py`
  - `services/dependencies/vendor_docs.py`
  - `services/mcp/tools.py`
- Ruff remains intentionally limited to `F,I`
- shared test database cleanup now uses a PostgreSQL advisory lock to avoid local deadlocks across overlapping `pytest` runs

Remaining:

- decide whether to widen Ruff beyond `F,I` after line-length debt is reduced
- decide whether to expand MyPy coverage beyond the current high-signal service set
- optionally add smoke execution to CI

## Suggested Execution Order

1. implement sync-state schema and idempotent ingest behavior
2. improve related-change ranking using richer metadata
3. add vendor docs multi-page discovery and batch sync
4. expand lint/type gates only after service behavior stabilizes

## Non-Goals for Phase 2

- no chat UI
- no code modification agent
- no custom vector database
- no broad third-party knowledge connectors
- no billing or admin backoffice
