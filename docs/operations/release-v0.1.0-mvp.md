# Repo + Dependency Context MCP v0.1.0-mvp

## Summary

Initial MVP release for Repo + Dependency Context MCP.

This release delivers an end-to-end context compiler flow for coding agents:

- repository code and Markdown ingest
- PR / issue / commit metadata ingest
- Python and Node dependency parsing
- official vendor docs whitelist ingest and fetch
- hybrid retrieval with evidence packing
- configurable embedding and rerank providers
- 4 MCP tools plus FastMCP stdio server
- offline eval runner
- playground, observability, smoke script, and demo seed flow
- CI workflow and basic quality gates

## Included Capabilities

### Ingest

- local repo ingest for code and docs
- GitHub-style metadata ingest for PRs, issues, and commits
- dependency parsing for `requirements.txt`, `pyproject.toml`, and `package.json`
- vendor doc ingest with strict official-domain whitelist enforcement

### Retrieval

- lexical + dense hybrid candidate generation
- evidence responses with:
  - `why_selected`
  - `authority`
  - `freshness_reason`
- query audit persistence in:
  - `query_logs`
  - `query_results`

### Interfaces

- internal REST API
- 4 MCP tools:
  - `search_context`
  - `get_source`
  - `get_related_changes`
  - `get_dependency_notes`
- FastMCP stdio server entrypoint

### Evaluation and Operations

- offline eval runner
- playground page
- observability metrics endpoint
- demo seed script
- smoke test script
- local runbook, demo script, release checklist, and handoff docs

## Validation

- database migration path verified with `python -m alembic upgrade head`
- full automated test suite green at release time
- GitHub Actions CI included

## Known MVP Limitations

- related changes matching is lightweight and metadata-based
- vendor doc fetcher is page-level, not crawler-level
- GitHub ingest does not yet track incremental sync state
- local embedding and rerank implementations are placeholders unless provider config is switched to OpenAI

## Tag

- `v0.1.0-mvp`
