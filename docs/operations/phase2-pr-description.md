# Phase 2 PR Description

## Title

`feat: harden sync, related changes, and vendor docs workflows`

## Summary

This PR advances the `phase2-hardening-and-sync` branch from MVP toward a more durable internal system.

It focuses on four areas:

- idempotent ingest and explicit ingest-job state
- stronger related-change metadata and ranking
- controlled vendor docs discovery and batch sync
- higher-signal CI type coverage and safer shared-test-db cleanup

## What Changed

### 1. Sync Hardening

- local repo ingest is now idempotent for unchanged sources
- change metadata ingest is now idempotent for repeated PR / issue / commit imports
- vendor doc ingest remains deduplicated across repeated fetch/discovery runs
- local ingest jobs now record:
  - `started_at`
  - `finished_at`
  - `completed` / `failed`
  - `failure_count`

### 2. Related Changes

- change chunks now carry richer metadata:
  - `related_file_paths`
  - `related_symbols`
  - `source_pr_ref`
  - `source_commit_sha`
  - `source_commit_ref`
  - `source_issue_ref`
- `get_related_changes` now uses deterministic ranking with this order:
  - exact path match
  - exact symbol match
  - path + symbol combined match
  - weaker lexical match
  - freshness as tie-breaker

### 3. Vendor Docs Discovery

- added controlled multi-page discovery from an index URL
- discovery remains restricted by:
  - official-domain whitelist
  - include URL prefixes
  - doc-type filtering
  - max page count
- added:
  - service-layer discovery API
  - Celery task entrypoint
  - CLI command: `rdcmcp vendor discover ...`

### 4. CI / Test Infrastructure

- focused MyPy coverage expanded to Phase 2 service surfaces
- CI docs updated to reflect current gate policy
- shared PostgreSQL test fixture now uses advisory locking during cleanup to avoid deadlocks across overlapping local test runs

## Validation

- `pytest` passes locally: `31 passed`
- focused MyPy passes for:
  - `config.py`
  - `services/ingest/change_metadata.py`
  - `services/ingest/github_metadata.py`
  - `services/dependencies/vendor_docs.py`
  - `services/mcp/tools.py`
  - `services/retrieval/embedding_provider.py`
  - `services/retrieval/rerank_provider.py`

## Notes

- Ruff intentionally remains limited to `F,I` in CI because broader enablement would currently create low-signal failures from existing line-length debt
- shared test DB cleanup is now serialized, but the suite is still not designed for meaningful parallel database execution
