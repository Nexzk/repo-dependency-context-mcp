# Commit Plan

This repository can be committed either as a single MVP snapshot or as a small sequence of logical commits.

## Recommended Split

### 1. `chore(scaffold): initialize repo dependency context mcp skeleton`

Include:

- project metadata and config
- FastAPI bootstrap
- logging and settings
- Docker Compose
- Alembic bootstrap
- basic health tests

Primary files:

- `pyproject.toml`
- `docker-compose.yml`
- `alembic.ini`
- `src/repo_dependency_context_mcp/main.py`
- `src/repo_dependency_context_mcp/config.py`
- `src/repo_dependency_context_mcp/db/*`
- `tests/unit/test_config.py`
- `tests/unit/test_health.py`

### 2. `feat(storage): add core schema and query audit models`

Include:

- ORM models
- initial Alembic migration
- model metadata tests

Primary files:

- `src/repo_dependency_context_mcp/db/models/*`
- `migrations/versions/20260322_0001_initial_schema.py`
- `tests/unit/test_models.py`

### 3. `feat(ingest): implement repo, dependency, and change metadata ingest`

Include:

- local repo ingest
- chunking
- dependency parser
- vendor doc ingest/fetch
- change metadata ingest
- GitHub metadata ingest

Primary files:

- `src/repo_dependency_context_mcp/services/ingest/*`
- `src/repo_dependency_context_mcp/services/chunking/*`
- `src/repo_dependency_context_mcp/services/dependencies/*`
- `tests/integration/test_local_repo_ingest.py`
- `tests/integration/test_dependency_ingest.py`
- `tests/integration/test_vendor_doc_ingest.py`
- `tests/integration/test_vendor_doc_fetcher.py`
- `tests/integration/test_github_metadata_ingest.py`
- `tests/integration/test_related_changes.py`

### 4. `feat(retrieval): add hybrid retrieval, evidence packing, and provider abstractions`

Include:

- embedding abstraction
- rerank abstraction
- search flow
- evidence packing

Primary files:

- `src/repo_dependency_context_mcp/services/retrieval/*`
- `src/repo_dependency_context_mcp/services/packing/*`
- `tests/integration/test_hybrid_retrieval.py`
- `tests/unit/test_embedding_provider.py`
- `tests/unit/test_rerank_provider.py`

### 5. `feat(interfaces): expose mcp tools, api routes, eval, and operations tooling`

Include:

- MCP tools and FastMCP server
- API routes
- eval runner
- Celery job wrappers
- playground and observability
- scripts and operations docs

Primary files:

- `src/repo_dependency_context_mcp/services/mcp/*`
- `src/repo_dependency_context_mcp/api/routes/*`
- `src/repo_dependency_context_mcp/services/eval/*`
- `src/repo_dependency_context_mcp/workers/*`
- `scripts/*`
- `docs/operations/*`
- `tests/integration/test_mcp_tools.py`
- `tests/integration/test_mcp_server.py`
- `tests/integration/test_eval_runner.py`
- `tests/integration/test_job_flows.py`
- `tests/integration/test_playground_observability.py`

## Single Commit Option

If you prefer one initial snapshot, use:

`feat(mvp): implement repo dependency context mcp end-to-end`

## Before Committing

- Exclude `src/*.egg-info`
- Confirm `pytest` is green
- Confirm `.env` is not staged
