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

## Useful Commands

```powershell
rdcmcp mcp stdio
rdcmcp github ingest <tenant_id> <repo_id> <owner> <repo_name> [base_url]
rdcmcp vendor fetch <package_name> <ecosystem> <url> <version_range>
rdcmcp vendor discover <package_name> <ecosystem> <index_url> <version_range>
rdcmcp eval run <dataset.yaml>
rdcmcp eval run <dataset.yaml> --baseline-dataset-name <dataset_name>
rdcmcp eval run <dataset.yaml> --candidate-profiles <p1,p2> --rerank-profiles <r1,r2>
rdcmcp eval run <dataset.yaml> --candidate-profiles <p1,p2> --rerank-profiles <r1,r2> --json-only
rdcmcp eval run <dataset.yaml> --candidate-profiles <p1,p2> --rerank-profiles <r1,r2> --table-only
```

`vendor discover` performs controlled multi-page vendor docs discovery using the configured official-domain whitelist, inferred doc types, URL-prefix filtering, and bounded page counts.
