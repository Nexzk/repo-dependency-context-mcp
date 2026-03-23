from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from repo_dependency_context_mcp.api.deps import get_db_session
from repo_dependency_context_mcp.services.eval.runner import EvalRunnerService

router = APIRouter(prefix="/api/eval", tags=["eval"])


class EvalRunRequest(BaseModel):
    dataset_path: str
    baseline_dataset_name: str | None = None


@router.post("/run")
def run_eval(request: EvalRunRequest) -> dict:
    with get_db_session() as session:
        return EvalRunnerService(session).run_from_yaml(
            Path(request.dataset_path),
            baseline_dataset_name=request.baseline_dataset_name,
        )
