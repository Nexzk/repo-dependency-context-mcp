from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import desc, select

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
    top_source_ok: float

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
            + self.top_source_ok
        ) / 6

    @property
    def overall_score(self) -> float:
        return (self.retrieval_score + self.evidence_contract_score) / 2


JSONDict = dict[str, Any]


class EvalRunnerService:
    def __init__(self, session) -> None:
        self.session = session
        self.tool_service = MCPToolService(session)

    def run_from_yaml(
        self,
        dataset_path: Path,
        baseline_dataset_name: str | None = None,
        dataset_name_override: str | None = None,
        dataset_metadata_override: JSONDict | None = None,
    ) -> dict:
        payload = yaml.safe_load(dataset_path.read_text(encoding="utf-8"))
        dataset_metadata: JSONDict = {
            "source_path": str(dataset_path),
            "base_dataset_name": payload["name"],
        }
        if dataset_metadata_override:
            dataset_metadata.update(dataset_metadata_override)
        dataset = EvalDataset(
            name=dataset_name_override or payload["name"],
            description=payload.get("description"),
            metadata_json=dataset_metadata,
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
        failing_checks_counter: Counter[str] = Counter()
        failed_case_count = 0

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
                    "expected_top_source": case_payload.get("expected_top_source"),
                },
                metadata_json={
                    "tool": case_payload.get("tool", "search_context"),
                    "requires_clarification": case_payload.get(
                        "requires_clarification",
                        False,
                    )
                },
            )
            self.session.add(eval_case)
            self.session.flush()

            response = self._execute_case(
                eval_case=eval_case,
                case_payload=case_payload,
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
                expected_top_source=case_payload.get("expected_top_source"),
            )
            diagnostics = self._build_diagnostics(
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
                expected_top_source=case_payload.get("expected_top_source"),
            )
            recalls.append(metrics.recall_at_5)
            reciprocal_ranks.append(metrics.mrr)
            retrieval_scores.append(metrics.retrieval_score)
            evidence_scores.append(metrics.evidence_contract_score)
            overall_scores.append(metrics.overall_score)
            if diagnostics["failed_checks"]:
                failed_case_count += 1
                failing_checks_counter.update(
                    item["check"] for item in diagnostics["failed_checks"]
                )

            self.session.add(
                EvalCaseResult(
                    eval_run_id=eval_run.id,
                    eval_case_id=eval_case.id,
                    recall_at_k=metrics.recall_at_5,
                    mrr=metrics.mrr,
                    leakage_count=0,
                    result_payload={
                        "evidence": response["evidence"],
                        "diagnostics": diagnostics,
                        "scores": {
                            "recall_at_5": metrics.recall_at_5,
                            "mrr": metrics.mrr,
                            "authority_match": metrics.authority_match,
                            "freshness_reason_match": metrics.freshness_reason_match,
                            "why_selected_match": metrics.why_selected_match,
                            "evidence_count_ok": metrics.evidence_count_ok,
                            "rank_order_ok": metrics.rank_order_ok,
                            "top_source_ok": metrics.top_source_ok,
                            "retrieval_score": metrics.retrieval_score,
                            "evidence_contract_score": metrics.evidence_contract_score,
                            "overall_score": metrics.overall_score,
                        },
                    },
                )
            )

        summary = {
            "case_count": len(recalls),
            "failed_case_count": failed_case_count,
            "failing_checks": dict(failing_checks_counter),
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
            "retrieval_profiles": {
                "candidate_profile": (
                    self.tool_service.search_service.settings.retrieval_candidate_profile
                ),
                "rerank_profile": (
                    self.tool_service.search_service.settings.retrieval_rerank_profile
                ),
            },
        }
        if dataset_metadata_override and "matrix" in dataset_metadata_override:
            summary["matrix"] = dataset_metadata_override["matrix"]
        eval_run.status = "completed"
        eval_run.summary_json = summary
        self.session.commit()
        selected_eval_comparison = self._build_selected_eval_comparison(
            current_run_id=eval_run.id,
            baseline_dataset_name=baseline_dataset_name,
        )
        if selected_eval_comparison is not None:
            summary["selected_eval_comparison"] = selected_eval_comparison
        return summary

    def run_profile_matrix(
        self,
        dataset_path: Path,
        candidate_profiles: list[str],
        rerank_profiles: list[str],
        baseline_dataset_name: str | None = None,
    ) -> dict:
        original_settings = self.tool_service.search_service.settings
        runs: list[dict[str, Any]] = []
        batch_id = uuid.uuid4().hex

        try:
            for candidate_profile in candidate_profiles:
                for rerank_profile in rerank_profiles:
                    self.tool_service.search_service.settings = replace(
                        original_settings,
                        retrieval_candidate_profile=candidate_profile,
                        retrieval_rerank_profile=rerank_profile,
                    )
                    dataset_name_override = (
                        f"{Path(dataset_path).stem}::"
                        f"{candidate_profile}::{rerank_profile}::{uuid.uuid4().hex[:8]}"
                    )
                    summary = self.run_from_yaml(
                        dataset_path,
                        baseline_dataset_name=baseline_dataset_name,
                        dataset_name_override=dataset_name_override,
                        dataset_metadata_override={
                            "matrix": {
                                "batch_id": batch_id,
                                "base_dataset_name": Path(dataset_path).stem,
                                "candidate_profile": candidate_profile,
                                "rerank_profile": rerank_profile,
                            }
                        },
                    )
                    runs.append(
                        {
                            "candidate_profile": candidate_profile,
                            "rerank_profile": rerank_profile,
                            "summary": summary,
                        }
                    )
        finally:
            self.tool_service.search_service.settings = original_settings

        comparison_table = [
            self._build_matrix_comparison_row(run)
            for run in runs
        ]
        best_run = self._select_best_matrix_run(runs, baseline_dataset_name)

        return {
            "mode": "matrix",
            "batch_id": batch_id,
            "run_count": len(runs),
            "runs": runs,
            "comparison_table": comparison_table,
            "best_run": best_run,
        }

    def _build_matrix_comparison_row(self, run: dict[str, Any]) -> dict[str, Any]:
        row = {
            "candidate_profile": run["candidate_profile"],
            "rerank_profile": run["rerank_profile"],
            "overall_score": run["summary"]["overall_score"],
            "retrieval_score": run["summary"]["retrieval_score"],
            "evidence_contract_score": run["summary"]["evidence_contract_score"],
            "failed_case_count": run["summary"]["failed_case_count"],
        }
        comparison = run["summary"].get("selected_eval_comparison")
        if comparison is not None:
            row.update(
                {
                    "baseline_source": comparison["baseline_source"],
                    "delta_overall_score": comparison["delta_overall_score"],
                    "delta_retrieval_score": comparison["delta_retrieval_score"],
                    "delta_evidence_contract_score": comparison[
                        "delta_evidence_contract_score"
                    ],
                    "delta_failed_case_count": comparison["delta_failed_case_count"],
                }
            )
        return row

    def _select_best_matrix_run(
        self,
        runs: list[dict[str, Any]],
        baseline_dataset_name: str | None,
    ) -> dict[str, Any] | None:
        if not runs:
            return None
        if baseline_dataset_name:
            return max(
                runs,
                key=lambda run: (
                    float(
                        run["summary"]
                        .get("selected_eval_comparison", {})
                        .get("delta_overall_score", float("-inf"))
                    ),
                    float(
                        run["summary"]
                        .get("selected_eval_comparison", {})
                        .get("delta_retrieval_score", float("-inf"))
                    ),
                    -int(
                        run["summary"]
                        .get("selected_eval_comparison", {})
                        .get("delta_failed_case_count", 0)
                    ),
                ),
            )
        return max(
            runs,
            key=lambda run: (
                run["summary"]["overall_score"],
                run["summary"]["retrieval_score"],
                -run["summary"]["failed_case_count"],
            ),
        )

    def _build_selected_eval_comparison(
        self,
        current_run_id: uuid.UUID,
        baseline_dataset_name: str | None,
    ) -> JSONDict | None:
        if baseline_dataset_name is None:
            return None

        current = self.session.get(EvalRun, current_run_id)
        if current is None:
            return None

        baseline = self.session.scalar(
            select(EvalRun)
            .join(EvalDataset, EvalDataset.id == EvalRun.dataset_id)
            .where(EvalDataset.name == baseline_dataset_name)
            .order_by(desc(EvalRun.created_at))
            .limit(1)
        )
        if baseline is None:
            return None

        current_summary = current.summary_json
        baseline_summary = baseline.summary_json
        return {
            "baseline_source": baseline_dataset_name,
            "current_dataset_id": str(current.dataset_id),
            "previous_dataset_id": str(baseline.dataset_id),
            "current_overall_score": float(current_summary.get("overall_score", 0.0)),
            "previous_overall_score": float(baseline_summary.get("overall_score", 0.0)),
            "delta_overall_score": float(current_summary.get("overall_score", 0.0))
            - float(baseline_summary.get("overall_score", 0.0)),
            "current_retrieval_score": float(
                current_summary.get("retrieval_score", 0.0)
            ),
            "previous_retrieval_score": float(
                baseline_summary.get("retrieval_score", 0.0)
            ),
            "delta_retrieval_score": float(current_summary.get("retrieval_score", 0.0))
            - float(baseline_summary.get("retrieval_score", 0.0)),
            "current_evidence_contract_score": float(
                current_summary.get("evidence_contract_score", 0.0)
            ),
            "previous_evidence_contract_score": float(
                baseline_summary.get("evidence_contract_score", 0.0)
            ),
            "delta_evidence_contract_score": float(
                current_summary.get("evidence_contract_score", 0.0)
            )
            - float(baseline_summary.get("evidence_contract_score", 0.0)),
            "current_failed_case_count": int(
                current_summary.get("failed_case_count", 0)
            ),
            "previous_failed_case_count": int(
                baseline_summary.get("failed_case_count", 0)
            ),
            "delta_failed_case_count": int(current_summary.get("failed_case_count", 0))
            - int(baseline_summary.get("failed_case_count", 0)),
            "current_failing_checks": current_summary.get("failing_checks", {}),
            "previous_failing_checks": baseline_summary.get("failing_checks", {}),
        }

    def _execute_case(self, eval_case: EvalCase, case_payload: dict) -> dict:
        tool_name = case_payload.get("tool", "search_context")
        if tool_name == "search_context":
            return self.tool_service.search_context(
                tenant_id=eval_case.tenant_id,
                repo_id=eval_case.repo_id,
                query=eval_case.query_text,
                task_type=eval_case.task_type,
                top_k=5,
            )
        if tool_name == "get_dependency_notes":
            return self.tool_service.get_dependency_notes(
                tenant_id=eval_case.tenant_id,
                repo_id=eval_case.repo_id,
                package_name=case_payload["package_name"],
                version_range=case_payload.get("version_range"),
                topic=case_payload.get("topic"),
                top_k=5,
            )
        raise ValueError(f"unsupported eval tool: {tool_name}")

    def _build_diagnostics(
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
        expected_top_source: str | None,
    ) -> JSONDict:
        source_keys = [f"{item['source_type']}:{item['path_or_url']}" for item in evidence]
        authorities = [str(item.get("authority", "")) for item in evidence]
        freshness_reasons = [str(item.get("freshness_reason", "")) for item in evidence]
        why_selected = [str(item.get("why_selected", "")) for item in evidence]

        failed_checks: list[JSONDict] = []
        if must_hit_sources and not any(source in source_keys for source in must_hit_sources):
            failed_checks.append(
                {
                    "check": "must_hit_sources",
                    "expected": must_hit_sources,
                    "actual": source_keys,
                }
            )
        unexpected_sources = [
            source for source in must_not_hit_sources if source in source_keys
        ]
        if unexpected_sources:
            failed_checks.append(
                {
                    "check": "must_not_hit_sources",
                    "expected": must_not_hit_sources,
                    "actual": unexpected_sources,
                }
            )
        missing_authorities = [
            authority for authority in expected_authorities if authority not in set(authorities)
        ]
        if missing_authorities:
            failed_checks.append(
                {
                    "check": "authority_match",
                    "expected": expected_authorities,
                    "actual": authorities,
                }
            )
        missing_freshness = _missing_expected_substrings(
            values=freshness_reasons,
            expected=expected_freshness_contains,
        )
        if missing_freshness:
            failed_checks.append(
                {
                    "check": "freshness_reason_match",
                    "expected": expected_freshness_contains,
                    "actual": freshness_reasons,
                }
            )
        missing_why = _missing_expected_substrings(
            values=why_selected,
            expected=expected_why_selected_contains,
        )
        if missing_why:
            failed_checks.append(
                {
                    "check": "why_selected_match",
                    "expected": expected_why_selected_contains,
                    "actual": why_selected,
                }
            )
        if min_evidence_count is not None and len(evidence) < min_evidence_count:
            failed_checks.append(
                {
                    "check": "evidence_count_ok",
                    "expected": {"min": min_evidence_count, "max": max_evidence_count},
                    "actual": len(evidence),
                }
            )
        if max_evidence_count is not None and len(evidence) > max_evidence_count:
            failed_checks.append(
                {
                    "check": "evidence_count_ok",
                    "expected": {"min": min_evidence_count, "max": max_evidence_count},
                    "actual": len(evidence),
                }
            )
        if _rank_order_ok(source_keys, must_rank_before) == 0.0:
            failed_checks.append(
                {
                    "check": "rank_order_ok",
                    "expected": must_rank_before,
                    "actual": source_keys,
                }
            )
        if _top_source_ok(source_keys, expected_top_source) == 0.0:
            failed_checks.append(
                {
                    "check": "top_source_ok",
                    "expected": expected_top_source,
                    "actual": source_keys[0] if source_keys else None,
                }
            )

        return {
            "failed_checks": failed_checks,
            "actual": {
                "source_keys": source_keys,
                "authorities": authorities,
                "freshness_reasons": freshness_reasons,
                "why_selected": why_selected,
            },
        }

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
        expected_top_source: str | None,
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
        top_source_ok = _top_source_ok(
            source_keys=source_keys,
            expected_top_source=expected_top_source,
        )

        return EvalMetrics(
            recall_at_5=recall,
            mrr=reciprocal_rank,
            authority_match=authority_match,
            freshness_reason_match=freshness_reason_match,
            why_selected_match=why_selected_match,
            evidence_count_ok=evidence_count_ok,
            rank_order_ok=rank_order_ok,
            top_source_ok=top_source_ok,
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


def _missing_expected_substrings(values: list[str], expected: list[str]) -> list[str]:
    if not expected:
        return []
    haystack = " ".join(values).lower()
    return [item for item in expected if item.lower() not in haystack]


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


def _top_source_ok(
    source_keys: list[str],
    expected_top_source: str | None,
) -> float:
    if not expected_top_source:
        return 1.0
    if not source_keys:
        return 0.0
    return 1.0 if source_keys[0] == expected_top_source else 0.0
