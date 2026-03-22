from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["playground"])


@router.get("/playground", response_class=HTMLResponse)
def playground() -> str:
    return """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Repo + Dependency Context MCP</title>
    <style>
      body { font-family: ui-sans-serif, system-ui, sans-serif; max-width: 840px; margin: 48px auto; padding: 0 24px; background: #f6f7fb; color: #1f2937; }
      .card { background: white; border-radius: 16px; padding: 24px; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08); }
      h1 { margin-top: 0; }
      code { background: #eef2ff; padding: 2px 6px; border-radius: 6px; }
      ul { line-height: 1.7; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Repo + Dependency Context MCP</h1>
      <p>Internal playground for validating the MVP retrieval pipeline.</p>
      <ul>
        <li>Search API: <code>POST /api/query/search</code></li>
        <li>Eval API: <code>POST /api/eval/run</code></li>
        <li>Metrics API: <code>GET /api/observability/metrics</code></li>
      </ul>
    </div>
  </body>
</html>
""".strip()
