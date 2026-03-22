# CI

The repository includes a minimal GitHub Actions workflow at `.github/workflows/ci.yml`.

## What It Does

- starts PostgreSQL with pgvector
- starts Redis
- installs project dependencies
- applies Alembic migrations
- seeds demo data for smoke
- starts the FastAPI app and waits for `/healthz`
- runs `scripts/smoke.ps1`
- runs `pytest`

## Current Scope

The workflow intentionally mirrors the current local MVP verification path.

The test suite still uses a shared PostgreSQL database. Test fixture setup now takes a PostgreSQL advisory lock before truncating tables, which prevents cross-process deadlocks if multiple local `pytest` runs overlap, but it does not make the suite meaningfully parallel.

It does not yet enforce:

- MCP transport smoke checks

## Why This Is Enough For Now

The highest-value signal for this MVP is still:

1. schema boots
2. services import
3. database-backed tests pass
4. end-to-end retrieval and eval flows stay green
5. basic live API smoke checks remain green

## Current Quality Gates

- `ruff check src tests scripts --select F,I`
- focused Ruff on:
  - `src/repo_dependency_context_mcp/services/ingest/change_metadata.py`
  - `src/repo_dependency_context_mcp/services/ingest/github_metadata.py`
  - `src/repo_dependency_context_mcp/services/dependencies/vendor_docs.py`
  - `src/repo_dependency_context_mcp/services/mcp/tools.py`
- focused MyPy on:
  - `src/repo_dependency_context_mcp/config.py`
  - `src/repo_dependency_context_mcp/services/ingest/change_metadata.py`
  - `src/repo_dependency_context_mcp/services/ingest/github_metadata.py`
  - `src/repo_dependency_context_mcp/services/dependencies/vendor_docs.py`
  - `src/repo_dependency_context_mcp/services/mcp/tools.py`
  - `src/repo_dependency_context_mcp/services/retrieval/embedding_provider.py`
  - `src/repo_dependency_context_mcp/services/retrieval/rerank_provider.py`

The MyPy scope is intentionally narrow because the repository still has broader MVP-grade typing debt. The current target set now covers:

- Phase 2 source files with tighter Ruff checks
- provider configuration and abstraction surfaces
- hardened ingest metadata paths
- vendor docs discovery and batch sync logic
- related-change ranking logic

Ruff still remains broad-only on `F,I`. The tighter `E,F,I,B` gate is intentionally limited to the Phase 2 source files above, where the debt has been reduced enough to keep CI high-signal.
