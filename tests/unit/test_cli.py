from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

from repo_dependency_context_mcp.cli import main as cli_main


def test_eval_run_cli_supports_profile_matrix(monkeypatch, capsys, tmp_path: Path) -> None:
    dataset_path = tmp_path / "eval.yaml"
    dataset_path.write_text("name: demo\ncases: []\n", encoding="utf-8")

    observed: dict[str, object] = {}

    @contextmanager
    def fake_db_session():
        yield object()

    class FakeRunner:
        def __init__(self, session) -> None:
            assert session is not None
            self.tool_service = type(
                "ToolService",
                (),
                {
                    "search_service": type(
                        "SearchService",
                        (),
                        {
                            "settings": type(
                                "SettingsStub",
                                (),
                                {
                                    "retrieval_candidate_profile": "hybrid_dual_route_v1",
                                    "retrieval_rerank_profile": "local_task_aware_v2",
                                },
                            )()
                        },
                    )()
                },
            )()

        def run_profile_matrix(
            self,
            dataset_path: Path,
            candidate_profiles: list[str],
            rerank_profiles: list[str],
            baseline_dataset_name: str | None = None,
        ) -> dict:
            observed["dataset_path"] = dataset_path
            observed["candidate_profiles"] = candidate_profiles
            observed["rerank_profiles"] = rerank_profiles
            observed["baseline_dataset_name"] = baseline_dataset_name
            return {
                "mode": "matrix",
                "run_count": 2,
                "comparison_table": [
                    {
                        "candidate_profile": "hybrid_dual_route_v1",
                        "rerank_profile": "local_task_aware_v2",
                        "overall_score": 0.7,
                        "retrieval_score": 0.8,
                        "evidence_contract_score": 0.6,
                        "failed_case_count": 1,
                    },
                    {
                        "candidate_profile": "hybrid_dual_route_dense_boost_v1",
                        "rerank_profile": "local_task_aware_v2",
                        "overall_score": 0.9,
                        "retrieval_score": 0.95,
                        "evidence_contract_score": 0.85,
                        "failed_case_count": 0,
                    },
                ],
                "best_run": {
                    "candidate_profile": "hybrid_dual_route_dense_boost_v1",
                    "rerank_profile": "local_task_aware_v2",
                },
            }

    monkeypatch.setattr(cli_main, "get_db_session", fake_db_session)
    monkeypatch.setattr(cli_main, "EvalRunnerService", FakeRunner)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rdcmcp",
            "eval",
            "run",
            str(dataset_path),
            "--baseline-dataset-name",
            "demo-baseline",
            "--candidate-profiles",
            "hybrid_dual_route_v1,hybrid_dual_route_dense_boost_v1",
            "--rerank-profiles",
            "local_task_aware_v2",
        ],
    )

    cli_main.main()

    captured = capsys.readouterr()
    assert "Eval Matrix Results" in captured.out
    assert "hybrid_dual_route_dense_boost_v1" in captured.out
    assert "*    | hybrid_dual_route_dense_boost_v1" in captured.out
    assert "'mode': 'matrix'" in captured.out
    assert observed["dataset_path"] == dataset_path
    assert observed["candidate_profiles"] == [
        "hybrid_dual_route_v1",
        "hybrid_dual_route_dense_boost_v1",
    ]
    assert observed["rerank_profiles"] == ["local_task_aware_v2"]
    assert observed["baseline_dataset_name"] == "demo-baseline"


def test_eval_run_cli_supports_json_only_for_matrix(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "eval_json.yaml"
    dataset_path.write_text("name: demo\ncases: []\n", encoding="utf-8")

    @contextmanager
    def fake_db_session():
        yield object()

    class FakeRunner:
        def __init__(self, session) -> None:
            self.tool_service = type(
                "ToolService",
                (),
                {
                    "search_service": type(
                        "SearchService",
                        (),
                        {
                            "settings": type(
                                "SettingsStub",
                                (),
                                {
                                    "retrieval_candidate_profile": "hybrid_dual_route_v1",
                                    "retrieval_rerank_profile": "local_task_aware_v2",
                                },
                            )()
                        },
                    )()
                },
            )()

        def run_profile_matrix(
            self,
            dataset_path: Path,
            candidate_profiles: list[str],
            rerank_profiles: list[str],
            baseline_dataset_name: str | None = None,
        ) -> dict:
            return {
                "mode": "matrix",
                "comparison_table": [
                    {
                        "candidate_profile": "hybrid_dual_route_v1",
                        "rerank_profile": "local_task_aware_v2",
                        "overall_score": 0.9,
                        "retrieval_score": 0.9,
                        "evidence_contract_score": 0.9,
                        "failed_case_count": 0,
                    }
                ],
                "best_run": {
                    "candidate_profile": "hybrid_dual_route_v1",
                    "rerank_profile": "local_task_aware_v2",
                },
            }

    monkeypatch.setattr(cli_main, "get_db_session", fake_db_session)
    monkeypatch.setattr(cli_main, "EvalRunnerService", FakeRunner)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rdcmcp",
            "eval",
            "run",
            str(dataset_path),
            "--candidate-profiles",
            "hybrid_dual_route_v1",
            "--rerank-profiles",
            "local_task_aware_v2",
            "--json-only",
        ],
    )

    cli_main.main()

    captured = capsys.readouterr()
    assert "Eval Matrix Results" not in captured.out
    assert "'mode': 'matrix'" in captured.out


def test_eval_run_cli_supports_table_only_for_matrix(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "eval_table.yaml"
    dataset_path.write_text("name: demo\ncases: []\n", encoding="utf-8")

    @contextmanager
    def fake_db_session():
        yield object()

    class FakeRunner:
        def __init__(self, session) -> None:
            self.tool_service = type(
                "ToolService",
                (),
                {
                    "search_service": type(
                        "SearchService",
                        (),
                        {
                            "settings": type(
                                "SettingsStub",
                                (),
                                {
                                    "retrieval_candidate_profile": "hybrid_dual_route_v1",
                                    "retrieval_rerank_profile": "local_task_aware_v2",
                                },
                            )()
                        },
                    )()
                },
            )()

        def run_profile_matrix(
            self,
            dataset_path: Path,
            candidate_profiles: list[str],
            rerank_profiles: list[str],
            baseline_dataset_name: str | None = None,
        ) -> dict:
            return {
                "mode": "matrix",
                "comparison_table": [
                    {
                        "candidate_profile": "hybrid_dual_route_v1",
                        "rerank_profile": "local_task_aware_v2",
                        "overall_score": 0.9,
                        "retrieval_score": 0.9,
                        "evidence_contract_score": 0.9,
                        "failed_case_count": 0,
                    }
                ],
                "best_run": {
                    "candidate_profile": "hybrid_dual_route_v1",
                    "rerank_profile": "local_task_aware_v2",
                },
            }

    monkeypatch.setattr(cli_main, "get_db_session", fake_db_session)
    monkeypatch.setattr(cli_main, "EvalRunnerService", FakeRunner)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rdcmcp",
            "eval",
            "run",
            str(dataset_path),
            "--candidate-profiles",
            "hybrid_dual_route_v1",
            "--rerank-profiles",
            "local_task_aware_v2",
            "--table-only",
        ],
    )

    cli_main.main()

    captured = capsys.readouterr()
    assert "Eval Matrix Results" in captured.out
    assert "'mode': 'matrix'" not in captured.out
