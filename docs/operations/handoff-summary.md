# Handoff Summary

## Current State

The repository is no longer just an MVP scaffold. The core ingest, retrieval, eval, and observability loop is implemented and wired together.

What exists now:

- PostgreSQL schema with query audit, eval, and durable sync-state tables
- Local repo ingest for code and Markdown, with snapshot-based sync state
- GitHub PR / issue / commit ingest with sync cursors and run history
- Python and Node dependency parsing
- Vendor docs whitelist ingest with bounded discovery and sync state
- Hybrid retrieval with dual-route candidate generation
- Configurable embedding and rerank providers
- Evidence packing with `why_selected`, `authority`, and `freshness_reason`
- 4 MCP tools and a FastMCP stdio server
- Offline eval runner with:
  - retrieval scoring
  - evidence contract scoring
  - source rank-order assertions
  - top-source assertions
  - per-case diagnostics
  - baseline comparison
  - profile-matrix execution
- Observability and playground surfaces for:
  - recent eval runs
  - recent failure aggregation
  - score trends
  - baseline comparison
  - latest matrix summary
- CLI and task entrypoints for matrix eval execution
- Demo seed script, smoke script, CI, and containerized local boot path

## Primary Entrypoints

- API:
  - `src/repo_dependency_context_mcp/api/`
- Services:
  - `src/repo_dependency_context_mcp/services/`
- Models:
  - `src/repo_dependency_context_mcp/db/models/`
- Workers:
  - `src/repo_dependency_context_mcp/workers/tasks/`
- CLI:
  - `src/repo_dependency_context_mcp/cli/main.py`
- Ops docs:
  - `docs/operations/`

## Fast Start

1. `docker-compose up -d`
2. `python -m alembic upgrade head`
3. `python .\scripts\seed_demo.py`
4. `uvicorn repo_dependency_context_mcp.main:app --reload --app-dir src`
5. `powershell -ExecutionPolicy Bypass -File .\scripts\smoke.ps1`

## Eval Experiment Loop

The shortest practical experiment loop is now:

1. run a dataset once:
   - `rdcmcp eval run <dataset.yaml>`
2. compare against a named baseline:
   - `rdcmcp eval run <dataset.yaml> --baseline-dataset-name <dataset_name>`
3. run a matrix across candidate/rerank profiles:
   - `rdcmcp eval run <dataset.yaml> --candidate-profiles <p1,p2> --rerank-profiles <r1,r2>`
4. choose an output mode depending on the consumer:
   - `--json-only`
   - `--table-only`
   - `--best-only`
   - `--failures-only`

## Current Retrieval Profiles

Candidate profiles:

- `hybrid_dual_route_v1`
- `hybrid_dual_route_dense_boost_v1`

Rerank profiles:

- `local_task_aware_v2`
- `local_task_aware_authority_boost_v1`

These profile names are recorded in query logs, eval summaries, observability outputs, and matrix comparisons.

## What Is Still Intentionally Lightweight

- default local embedding and local rerank implementations are still placeholder-quality compared with external providers
- vendor docs ingest is bounded discovery/sync, not crawler-level site ingestion
- `get_related_changes` is still metadata/ranking driven, not graph-based change intelligence
- CI does not separately exercise every manual matrix CLI presentation mode

## Best Reference Docs

- local setup and commands:
  - `docs/operations/local-runbook.md`
- demo flow:
  - `docs/operations/demo-script.md`
- release checks:
  - `docs/operations/release-checklist.md`
- CI scope:
  - `docs/operations/ci.md`
