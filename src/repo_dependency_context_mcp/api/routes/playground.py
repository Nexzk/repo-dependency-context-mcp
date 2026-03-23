from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from repo_dependency_context_mcp.api.deps import get_db_session
from repo_dependency_context_mcp.api.routes.observability import (
    build_latest_eval_comparison,
    build_latest_eval_matrix_summary,
    list_latest_eval_failures,
    list_latest_eval_runs,
)

router = APIRouter(tags=["playground"])


@router.get("/playground", response_class=HTMLResponse)
def playground() -> str:
    with get_db_session() as session:
        latest_runs = list_latest_eval_runs(session, limit=1)
        latest_failures = list_latest_eval_failures(session)
        comparison_runs = list_latest_eval_runs(session, limit=20)
        latest_eval_comparison = build_latest_eval_comparison(comparison_runs)
        latest_eval_matrix_summary = build_latest_eval_matrix_summary(comparison_runs)

    latest_eval_html = "<p>No eval runs yet.</p>"
    if latest_runs:
        latest_run = latest_runs[0]
        overall_score = latest_run.summary_json.get("overall_score", 0.0)
        failed_case_count = latest_run.summary_json.get("failed_case_count", 0)
        failing_checks = latest_run.summary_json.get("failing_checks", {})
        latest_eval_html = f"""
      <div class="section">
        <h2>Latest Eval</h2>
        <p><strong>Overall score:</strong> {overall_score}</p>
        <p><strong>Failed cases:</strong> {failed_case_count}</p>
        <p><strong>Failing checks:</strong> <code>{failing_checks}</code></p>
      </div>
"""
        if latest_failures:
            failure_items = []
            for failure in latest_failures:
                failure_items.append(
                    f"""
        <li>
          <strong>{failure["case_name"]}</strong><br />
          <span>{failure["query_text"]}</span><br />
          <code>{failure["failed_checks"]}</code><br />
          <code>{failure["top_evidence_sources"]}</code>
        </li>
"""
                )
            latest_eval_html += f"""
      <div class="section">
        <h2>Latest Eval Failures</h2>
        <ul>
          {''.join(failure_items)}
        </ul>
      </div>
"""
        if latest_eval_comparison:
            evidence_delta = latest_eval_comparison["delta_evidence_contract_score"]
            failed_case_delta = latest_eval_comparison["delta_failed_case_count"]
            latest_eval_html += f"""
      <div class="section">
        <h2>Latest Eval Comparison</h2>
        <p><strong>Overall delta:</strong> {latest_eval_comparison["delta_overall_score"]}</p>
        <p><strong>Retrieval delta:</strong> {latest_eval_comparison["delta_retrieval_score"]}</p>
        <p><strong>Evidence delta:</strong> {evidence_delta}</p>
        <p><strong>Failed-case delta:</strong> {failed_case_delta}</p>
      </div>
"""
        if latest_eval_matrix_summary:
            best_run = latest_eval_matrix_summary["best_run"]
            latest_eval_html += f"""
      <div class="section">
        <h2>Best Matrix Profile</h2>
        <p><strong>Batch:</strong> <code>{latest_eval_matrix_summary["batch_id"]}</code></p>
        <p><strong>Runs:</strong> {latest_eval_matrix_summary["run_count"]}</p>
        <p><strong>Candidate profile:</strong> <code>{best_run["candidate_profile"]}</code></p>
        <p><strong>Rerank profile:</strong> <code>{best_run["rerank_profile"]}</code></p>
        <p><strong>Overall score:</strong> {best_run["overall_score"]}</p>
      </div>
"""

    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Repo + Dependency Context MCP</title>
    <style>
      body {{
        font-family: ui-sans-serif, system-ui, sans-serif;
        max-width: 840px;
        margin: 48px auto;
        padding: 0 24px;
        background: #f6f7fb;
        color: #1f2937;
      }}
      .card {{
        background: white;
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
      }}
      h1 {{ margin-top: 0; }}
      h2 {{ margin-bottom: 8px; }}
      code {{ background: #eef2ff; padding: 2px 6px; border-radius: 6px; }}
      ul {{ line-height: 1.7; }}
      .section {{ margin-top: 24px; }}
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
        <li>
          Sync State:
          <code>latest_sync_runs</code>
          and
          <code>latest_sync_cursors</code>
          in metrics
        </li>
      </ul>
{latest_eval_html}
    </div>
  </body>
</html>
""".strip()
