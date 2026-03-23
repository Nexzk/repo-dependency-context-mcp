# MVP Release Checklist

Use this checklist before handing the repository to another engineer or running a demo.

## Environment

- [ ] `.env` exists and matches the target environment
- [ ] `RDCMCP_DATABASE_URL` points to a PostgreSQL instance with `pgvector`
- [ ] `RDCMCP_REDIS_URL` points to a reachable Redis instance
- [ ] If using OpenAI providers:
  - [ ] `RDCMCP_OPENAI_API_KEY` is set
  - [ ] `RDCMCP_EMBEDDING_PROVIDER` is set correctly
  - [ ] `RDCMCP_RERANK_PROVIDER` is set correctly

## Database

- [ ] `python -m alembic upgrade head` completes successfully
- [ ] Core tables exist:
  - [ ] `sources`
  - [ ] `documents`
  - [ ] `chunks`
  - [ ] `dependencies`
  - [ ] `dependency_docs`
  - [ ] `query_logs`
  - [ ] `query_results`
  - [ ] `eval_runs`

## Runtime

- [ ] API server starts with `uvicorn repo_dependency_context_mcp.main:app --reload --app-dir src`
- [ ] `GET /healthz` returns `status=ok`
- [ ] `GET /playground` returns `200`
- [ ] `GET /api/observability/metrics` returns JSON counters

## Core Product Flow

- [ ] Local repo ingest works
- [ ] Code and Markdown chunks are persisted
- [ ] Query returns evidence with:
  - [ ] `why_selected`
  - [ ] `authority`
  - [ ] `freshness_reason`
- [ ] Query audit rows are persisted in:
  - [ ] `query_logs`
  - [ ] `query_results`

## Dependency Flow

- [ ] Python dependency parsing works
- [ ] Node dependency parsing works
- [ ] Vendor docs are accepted only for whitelisted domains
- [ ] Vendor doc notes appear in `get_dependency_notes`

## Related Changes Flow

- [ ] PR metadata ingest works
- [ ] Issue metadata ingest works
- [ ] Commit metadata ingest works
- [ ] `get_related_changes` returns structured summaries

## MCP

- [ ] `rdcmcp mcp stdio` starts without crashing
- [ ] MCP server lists 4 tools:
  - [ ] `search_context`
  - [ ] `get_source`
  - [ ] `get_related_changes`
  - [ ] `get_dependency_notes`

## Eval

- [ ] `rdcmcp eval run <dataset.yaml>` completes successfully
- [ ] Baseline eval comparison works:
  - [ ] `rdcmcp eval run <dataset.yaml> --baseline-dataset-name <dataset_name>`
- [ ] Matrix eval works:
  - [ ] `rdcmcp eval run <dataset.yaml> --candidate-profiles <p1,p2> --rerank-profiles <r1,r2>`
- [ ] Baseline-aware matrix eval works:
  - [ ] `rdcmcp eval run <dataset.yaml> --baseline-dataset-name <dataset_name> --candidate-profiles <p1,p2> --rerank-profiles <r1,r2> --table-only`
  - [ ] Matrix output includes baseline delta columns:
    - [ ] `d_overall`
    - [ ] `d_retrieval`
    - [ ] `d_evidence`
    - [ ] `d_failed`
- [ ] Matrix output modes work as expected:
  - [ ] `--json-only`
  - [ ] `--table-only`
  - [ ] `--best-only`
  - [ ] `--failures-only`
- [ ] Eval rows are written to `eval_runs` and `eval_case_results`
- [ ] Demo eval can hit at least one required evidence source

## Demo Readiness

- [ ] `python .\scripts\seed_demo.py` completes successfully
- [ ] Smoke script runs:
  - [ ] `powershell -ExecutionPolicy Bypass -File .\scripts\smoke.ps1`
- [ ] Demo tenant and repo IDs are available for API calls

## Security

- [ ] Tenant/repo scoped queries do not return cross-repo data
- [ ] OpenAI provider config fails fast when key is missing
- [ ] Vendor docs fetch rejects non-whitelisted domains

## Current Known Gaps

- [ ] `get_related_changes` uses MVP-grade matching, not full graph/link analysis
- [ ] Vendor doc fetcher is bounded discovery/sync, not full crawler-level site ingestion
- [ ] Dense retrieval and rerank support provider abstraction, but default local implementations are lightweight placeholders
