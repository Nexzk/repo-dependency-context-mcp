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
    candidate_profiles: list[str] | None = None
    rerank_profiles: list[str] | None = None


@router.post("/run")
def run_eval(request: EvalRunRequest) -> dict:
    with get_db_session() as session:
        runner = EvalRunnerService(session)
        if request.candidate_profiles or request.rerank_profiles:
            settings = runner.tool_service.search_service.settings
            return runner.run_profile_matrix(
                Path(request.dataset_path),
                candidate_profiles=request.candidate_profiles
                or [settings.retrieval_candidate_profile],
                rerank_profiles=request.rerank_profiles
                or [settings.retrieval_rerank_profile],
                baseline_dataset_name=request.baseline_dataset_name,
            )
        return runner.run_from_yaml(
            Path(request.dataset_path),
            baseline_dataset_name=request.baseline_dataset_name,
        )
