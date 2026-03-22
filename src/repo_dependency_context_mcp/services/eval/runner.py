from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml

from repo_dependency_context_mcp.db.models import EvalCase, EvalCaseResult, EvalDataset, EvalRun
from repo_dependency_context_mcp.services.mcp.tools import MCPToolService


@dataclass(slots=True)
class EvalMetrics:
    recall_at_5: float
    mrr: float


class EvalRunnerService:
    def __init__(self, session) -> None:
        self.session = session
        self.tool_service = MCPToolService(session)

    def run_from_yaml(self, dataset_path: Path) -> dict:
        payload = yaml.safe_load(dataset_path.read_text(encoding="utf-8"))
        dataset = EvalDataset(
            name=payload["name"],
            description=payload.get("description"),
            metadata_json={"source_path": str(dataset_path)},
        )
        self.session.add(dataset)
        self.session.flush()

        eval_run = EvalRun(dataset_id=dataset.id, status="running", summary_json={})
        self.session.add(eval_run)
        self.session.flush()

        recalls: list[float] = []
        reciprocal_ranks: list[float] = []

        for case_payload in payload.get("cases", []):
            eval_case = EvalCase(
                dataset_id=dataset.id,
                tenant_id=uuid.UUID(case_payload["tenant_id"]),
                repo_id=uuid.UUID(case_payload["repo_id"]) if case_payload.get("repo_id") else None,
                name=case_payload["id"],
                query_text=case_payload["query"],
                task_type=case_payload.get("task_type"),
                expected_evidence={
                    "must_hit_sources": case_payload.get("must_hit_sources", []),
                    "acceptable_sources": case_payload.get("acceptable_sources", []),
                    "must_not_hit_sources": case_payload.get("must_not_hit_sources", []),
                },
                metadata_json={"requires_clarification": case_payload.get("requires_clarification", False)},
            )
            self.session.add(eval_case)
            self.session.flush()

            response = self.tool_service.search_context(
                tenant_id=eval_case.tenant_id,
                repo_id=eval_case.repo_id,
                query=eval_case.query_text,
                task_type=eval_case.task_type,
                top_k=5,
            )

            metrics = self._score_case(
                evidence=response["evidence"],
                must_hit_sources=case_payload.get("must_hit_sources", []),
                must_not_hit_sources=case_payload.get("must_not_hit_sources", []),
            )
            recalls.append(metrics.recall_at_5)
            reciprocal_ranks.append(metrics.mrr)

            self.session.add(
                EvalCaseResult(
                    eval_run_id=eval_run.id,
                    eval_case_id=eval_case.id,
                    recall_at_k=metrics.recall_at_5,
                    mrr=metrics.mrr,
                    leakage_count=0,
                    result_payload={"evidence": response["evidence"]},
                )
            )

        summary = {
            "case_count": len(recalls),
            "recall_at_5": sum(recalls) / len(recalls) if recalls else 0.0,
            "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0.0,
        }
        eval_run.status = "completed"
        eval_run.summary_json = summary
        self.session.commit()
        return summary

    def _score_case(self, evidence: list[dict], must_hit_sources: list[str], must_not_hit_sources: list[str]) -> EvalMetrics:
        source_keys = [f"{item['source_type']}:{item['path_or_url']}" for item in evidence]
        recall = 1.0 if any(source in source_keys for source in must_hit_sources) else 0.0

        reciprocal_rank = 0.0
        for index, source_key in enumerate(source_keys, start=1):
            if source_key in must_hit_sources:
                reciprocal_rank = 1.0 / index
                break

        leakage = any(source in source_keys for source in must_not_hit_sources)
        if leakage:
            recall = 0.0
            reciprocal_rank = 0.0

        return EvalMetrics(recall_at_5=recall, mrr=reciprocal_rank)
