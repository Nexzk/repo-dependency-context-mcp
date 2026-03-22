# Demo Script

This is the shortest reliable demo path for the current MVP.

## 1. Start Infra

```powershell
docker-compose up -d
python -m alembic upgrade head
```

## 2. Seed Demo Data

```powershell
python .\scripts\seed_demo.py
```

Capture the printed:

- `tenant_id`
- `repo_id`

Set them for later smoke checks:

```powershell
$env:RDCMCP_SMOKE_TENANT_ID="<tenant_id>"
$env:RDCMCP_SMOKE_REPO_ID="<repo_id>"
```

## 3. Start API

```powershell
uvicorn repo_dependency_context_mcp.main:app --reload --app-dir src
```

## 4. Show Health and Playground

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz
Start-Process http://127.0.0.1:8000/playground
```

## 5. Show Search

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/query/search `
  -ContentType "application/json" `
  -Body (@{
    tenant_id = $env:RDCMCP_SMOKE_TENANT_ID
    repo_id = $env:RDCMCP_SMOKE_REPO_ID
    query = "where is admin authorization logic"
    task_type = "locate"
    top_k = 3
  } | ConvertTo-Json)
```

Expected outcome:

- Evidence points at `src/auth.py`
- Evidence includes `why_selected`, `authority`, and `freshness_reason`

## 6. Show Metrics

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/observability/metrics
```

Expected outcome:

- Non-zero `query_logs`
- Non-zero `eval_runs`

## 7. Show MCP Server

In another terminal:

```powershell
rdcmcp mcp stdio
```

Expected outcome:

- Server starts without crashing
- MCP client can discover the 4 registered tools

## 8. Optional Smoke Script

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\smoke.ps1
```
