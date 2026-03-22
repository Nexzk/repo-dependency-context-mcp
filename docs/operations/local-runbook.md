# Local Runbook

This runbook covers the minimum steps to boot, verify, and exercise the Repo + Dependency Context MCP MVP in a local development environment.

## Prerequisites

- Python 3.11+
- PostgreSQL with pgvector enabled
- Redis
- Project dependencies installed with `python -m pip install -e ".[dev]"`

## Environment

1. Copy `.env.example` to `.env`
2. Set `RDCMCP_DATABASE_URL`
3. Set `RDCMCP_REDIS_URL`
4. If using OpenAI providers, set:
   - `RDCMCP_OPENAI_API_KEY`
   - `RDCMCP_EMBEDDING_PROVIDER=openai`
   - `RDCMCP_RERANK_PROVIDER=openai`

## Boot Services

1. Start local infra:

```powershell
docker-compose up -d
```

Or start infra plus API together:

```powershell
docker-compose up -d --build
```

2. Apply database migrations:

```powershell
python -m alembic upgrade head
```

3. Start the API server:

```powershell
uvicorn repo_dependency_context_mcp.main:app --reload --app-dir src
```

If you started the `app` container in Docker Compose, you can skip this manual API step.

4. Optional: start the MCP server on stdio:

```powershell
rdcmcp mcp stdio
```

## Verification

Run tests:

```powershell
pytest
```

Run the smoke script against a live local server:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke.ps1
```

Seed a demo dataset:

```powershell
python .\scripts\seed_demo.py
```

Use the printed `tenant_id` and `repo_id` as:

```powershell
$env:RDCMCP_SMOKE_TENANT_ID="<printed-tenant-id>"
$env:RDCMCP_SMOKE_REPO_ID="<printed-repo-id>"
```

## Important Endpoints

- `GET /healthz`
- `POST /api/query/search`
- `POST /api/eval/run`
- `GET /api/observability/metrics`
- `GET /playground`

## Common Failure Modes

- Provider validation failure on startup:
  - Happens when `RDCMCP_EMBEDDING_PROVIDER=openai` or `RDCMCP_RERANK_PROVIDER=openai` but `RDCMCP_OPENAI_API_KEY` is missing.
- Empty retrieval results:
  - Usually means repo ingest or dependency ingest has not been run yet.
- Vendor doc fetch rejected:
  - Check the package-to-domain whitelist and confirm the URL host matches it exactly.

## Suggested Demo Order

1. `GET /healthz`
2. Local repo ingest
3. Query via `POST /api/query/search`
4. Run eval with `rdcmcp eval run <dataset.yaml>`
5. Inspect `GET /api/observability/metrics`

For a structured demo path, see `docs/operations/demo-script.md`.
For release validation, see `docs/operations/release-checklist.md`.
For automated verification, see `docs/operations/ci.md`.
