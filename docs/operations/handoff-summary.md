# Handoff Summary

## What Exists

- PostgreSQL schema with query audit and eval tables
- Local repo ingest for code and Markdown
- Change metadata ingest for PR, issue, and commit summaries
- GitHub-style metadata fetcher
- Dependency parsing for Python and Node
- Vendor docs whitelist ingest and single-page fetcher
- Hybrid retrieval with configurable embedding and rerank providers
- Evidence packing with `why_selected`, `authority`, and `freshness_reason`
- 4 MCP tools and a FastMCP stdio server
- Offline eval runner
- Playground and observability endpoints
- Celery task wrappers and CLI commands
- Demo seed script and smoke test

## What Is Still MVP-Grade

- Local embedding and local rerank are placeholders
- Vendor doc fetch is page-level, not crawler-level
- GitHub ingest has no incremental sync cursor/state
- Related changes matching is lexical/metadata based, not graph-based

## Fast Start

1. `docker-compose up -d`
2. `python -m alembic upgrade head`
3. `python .\scripts\seed_demo.py`
4. `uvicorn repo_dependency_context_mcp.main:app --reload --app-dir src`
5. `powershell -ExecutionPolicy Bypass -File .\scripts\smoke.ps1`

## Primary Paths

- API: `src/repo_dependency_context_mcp/api/`
- Services: `src/repo_dependency_context_mcp/services/`
- Models: `src/repo_dependency_context_mcp/db/models/`
- Ops docs: `docs/operations/`
- Demo and smoke: `scripts/`
