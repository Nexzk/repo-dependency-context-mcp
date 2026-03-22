# CI

The repository includes a minimal GitHub Actions workflow at `.github/workflows/ci.yml`.

## What It Does

- starts PostgreSQL with pgvector
- starts Redis
- installs project dependencies
- applies Alembic migrations
- runs `pytest`

## Current Scope

The workflow intentionally mirrors the current local MVP verification path.

It does not yet enforce:

- smoke script execution
- MCP transport smoke checks

## Why This Is Enough For Now

The highest-value signal for this MVP is still:

1. schema boots
2. services import
3. database-backed tests pass
4. end-to-end retrieval and eval flows stay green

## Current Quality Gates

- `ruff check src tests scripts --select F,I`
- focused MyPy on:
  - `src/repo_dependency_context_mcp/config.py`
  - `src/repo_dependency_context_mcp/services/ingest/change_metadata.py`
  - `src/repo_dependency_context_mcp/services/ingest/github_metadata.py`
  - `src/repo_dependency_context_mcp/services/dependencies/vendor_docs.py`
  - `src/repo_dependency_context_mcp/services/mcp/tools.py`
  - `src/repo_dependency_context_mcp/services/retrieval/embedding_provider.py`
  - `src/repo_dependency_context_mcp/services/retrieval/rerank_provider.py`

The MyPy scope is intentionally narrow because the repository still has broader MVP-grade typing debt. The current target set now covers:

- provider configuration and abstraction surfaces
- hardened ingest metadata paths
- vendor docs discovery and batch sync logic
- related-change ranking logic

Ruff intentionally remains on `F,I` only. Expanding it to include `E` right now would turn CI noisy because the repository still has broad line-length debt that does not materially affect runtime correctness.
