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
    authority_match: float
    freshness_reason_match: float
    why_selected_match: float
    evidence_count_ok: float
    rank_order_ok: float

    @property
    def retrieval_score(self) -> float:
        return (self.recall_at_5 + self.mrr) / 2

    @property
    def evidence_contract_score(self) -> float:
        return (
            self.authority_match
            + self.freshness_reason_match
            + self.why_selected_match
            + self.evidence_count_ok
            + self.rank_order_ok
        ) / 5

    @property
    def overall_score(self) -> float:
        return (self.retrieval_score + self.evidence_contract_score) / 2


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
        retrieval_scores: list[float] = []
        evidence_scores: list[float] = []
        overall_scores: list[float] = []

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
                    "must_rank_before": case_payload.get("must_rank_before", []),
                },
                metadata_json={
                    "requires_clarification": case_payload.get(
                        "requires_clarification",
                        False,
                    )
                },
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
                expected_authorities=case_payload.get("expected_authorities", []),
                expected_freshness_contains=case_payload.get(
                    "expected_freshness_contains",
                    [],
                ),
                expected_why_selected_contains=case_payload.get(
                    "expected_why_selected_contains",
                    [],
                ),
                min_evidence_count=case_payload.get("min_evidence_count"),
                max_evidence_count=case_payload.get("max_evidence_count"),
                must_rank_before=case_payload.get("must_rank_before", []),
            )
            recalls.append(metrics.recall_at_5)
            reciprocal_ranks.append(metrics.mrr)
            retrieval_scores.append(metrics.retrieval_score)
            evidence_scores.append(metrics.evidence_contract_score)
            overall_scores.append(metrics.overall_score)

            self.session.add(
                EvalCaseResult(
                    eval_run_id=eval_run.id,
                    eval_case_id=eval_case.id,
                    recall_at_k=metrics.recall_at_5,
                    mrr=metrics.mrr,
                    leakage_count=0,
                    result_payload={
                        "evidence": response["evidence"],
                        "scores": {
                            "recall_at_5": metrics.recall_at_5,
                            "mrr": metrics.mrr,
                            "authority_match": metrics.authority_match,
                            "freshness_reason_match": metrics.freshness_reason_match,
                            "why_selected_match": metrics.why_selected_match,
                            "evidence_count_ok": metrics.evidence_count_ok,
                            "rank_order_ok": metrics.rank_order_ok,
                            "retrieval_score": metrics.retrieval_score,
                            "evidence_contract_score": metrics.evidence_contract_score,
                            "overall_score": metrics.overall_score,
                        },
                    },
                )
            )

        summary = {
            "case_count": len(recalls),
            "recall_at_5": sum(recalls) / len(recalls) if recalls else 0.0,
            "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks) if reciprocal_ranks else 0.0,
            "retrieval_score": (
                sum(retrieval_scores) / len(retrieval_scores)
                if retrieval_scores
                else 0.0
            ),
            "evidence_contract_score": (
                sum(evidence_scores) / len(evidence_scores)
                if evidence_scores
                else 0.0
            ),
            "overall_score": sum(overall_scores) / len(overall_scores) if overall_scores else 0.0,
        }
        eval_run.status = "completed"
        eval_run.summary_json = summary
        self.session.commit()
        return summary

    def _score_case(
        self,
        evidence: list[dict],
        must_hit_sources: list[str],
        must_not_hit_sources: list[str],
        expected_authorities: list[str],
        expected_freshness_contains: list[str],
        expected_why_selected_contains: list[str],
        min_evidence_count: int | None,
        max_evidence_count: int | None,
        must_rank_before: list[dict[str, str]],
    ) -> EvalMetrics:
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

        authority_match = _all_expected_match(
            values=[str(item.get("authority", "")) for item in evidence],
            expected=expected_authorities,
        )
        freshness_reason_match = _all_expected_substrings_match(
            values=[str(item.get("freshness_reason", "")) for item in evidence],
            expected=expected_freshness_contains,
        )
        why_selected_match = _all_expected_substrings_match(
            values=[str(item.get("why_selected", "")) for item in evidence],
            expected=expected_why_selected_contains,
        )
        evidence_count_ok = _evidence_count_ok(
            actual_count=len(evidence),
            min_count=min_evidence_count,
            max_count=max_evidence_count,
        )
        rank_order_ok = _rank_order_ok(
            source_keys=source_keys,
            must_rank_before=must_rank_before,
        )

        return EvalMetrics(
            recall_at_5=recall,
            mrr=reciprocal_rank,
            authority_match=authority_match,
            freshness_reason_match=freshness_reason_match,
            why_selected_match=why_selected_match,
            evidence_count_ok=evidence_count_ok,
            rank_order_ok=rank_order_ok,
        )


def _all_expected_match(values: list[str], expected: list[str]) -> float:
    if not expected:
        return 1.0
    value_set = set(values)
    return 1.0 if all(item in value_set for item in expected) else 0.0


def _all_expected_substrings_match(values: list[str], expected: list[str]) -> float:
    if not expected:
        return 1.0
    haystack = " ".join(values).lower()
    return 1.0 if all(item.lower() in haystack for item in expected) else 0.0


def _evidence_count_ok(
    actual_count: int,
    min_count: int | None,
    max_count: int | None,
) -> float:
    if min_count is not None and actual_count < min_count:
        return 0.0
    if max_count is not None and actual_count > max_count:
        return 0.0
    return 1.0


def _rank_order_ok(
    source_keys: list[str],
    must_rank_before: list[dict[str, str]],
) -> float:
    if not must_rank_before:
        return 1.0

    positions = {source_key: index for index, source_key in enumerate(source_keys)}
    for constraint in must_rank_before:
        higher = constraint.get("higher")
        lower = constraint.get("lower")
        if not higher or not lower:
            return 0.0
        if higher not in positions or lower not in positions:
            return 0.0
        if positions[higher] >= positions[lower]:
            return 0.0
    return 1.0
