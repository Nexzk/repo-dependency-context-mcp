# Repo + Dependency Context MCP

MVP scaffold for a context compiler that returns minimal evidence packs for coding agents.

## Phase 1 scope

- FastAPI app bootstrap
- Settings and logging bootstrap
- Database and Alembic bootstrap
- Celery bootstrap
- Minimal CLI entrypoint
- Minimal test suite

## Local development

1. Copy `.env.example` to `.env`
2. Start dependencies with `docker-compose up -d`
3. Run the app with `uvicorn repo_dependency_context_mcp.main:app --reload --app-dir src`
4. Run tests with `pytest`
5. Run the smoke script with `powershell -ExecutionPolicy Bypass -File .\scripts\smoke.ps1`

See `docs/operations/local-runbook.md` for a fuller local runbook.
