from __future__ import annotations

import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

from repo_dependency_context_mcp.api.deps import get_db_session
from repo_dependency_context_mcp.config import Settings
from repo_dependency_context_mcp.services.dependencies.vendor_docs import (
    VendorDocDiscoveryRequest,
    VendorDocFetchRequest,
    VendorDocIngestService,
)
from repo_dependency_context_mcp.services.eval.runner import EvalRunnerService
from repo_dependency_context_mcp.services.ingest.github_metadata import GitHubMetadataIngestService
from repo_dependency_context_mcp.services.mcp.server import build_mcp_server


def _parse_flag_value(args: list[str], flag: str) -> str | None:
    if flag not in args:
        return None
    index = args.index(flag)
    if index + 1 >= len(args):
        return None
    return args[index + 1]


def _parse_csv_flag(args: list[str], flag: str) -> list[str] | None:
    value = _parse_flag_value(args, flag)
    if value is None:
        return None
    values = [item.strip() for item in value.split(",") if item.strip()]
    return values or None


def main() -> None:
    settings = Settings()
    if len(sys.argv) >= 3 and sys.argv[1:3] == ["mcp", "stdio"]:
        build_mcp_server(get_db_session).run("stdio")
        return
    if len(sys.argv) >= 7 and sys.argv[1:3] == ["github", "ingest"]:
        tenant_id, repo_id, owner, repo_name = sys.argv[3:7]
        base_url = sys.argv[7] if len(sys.argv) >= 8 else "https://api.github.com"
        with get_db_session() as session:
            result = GitHubMetadataIngestService(session, base_url=base_url).ingest_repo_changes(
                tenant_id=uuid.UUID(tenant_id),
                repo_id=uuid.UUID(repo_id),
                owner=owner,
                repo_name=repo_name,
                acl_scope={"visibility": "private"},
            )
        print(result)
        return
    if len(sys.argv) >= 7 and sys.argv[1:3] == ["vendor", "fetch"]:
        package_name, ecosystem, url, version_range = sys.argv[3:7]
        hostname = urlparse(url).hostname or ""
        with get_db_session() as session:
            result = VendorDocIngestService(
                session,
                official_domains={package_name: [hostname]},
            ).fetch_and_ingest(
                package_name=package_name,
                ecosystem=ecosystem,
                requests=[
                    VendorDocFetchRequest(
                        doc_type="release_notes",
                        url=url,
                        version_range=version_range,
                    )
                ],
            )
        print(result)
        return
    if len(sys.argv) >= 7 and sys.argv[1:3] == ["vendor", "discover"]:
        package_name, ecosystem, index_url, version_range = sys.argv[3:7]
        hostname = urlparse(index_url).hostname or ""
        base_prefix = index_url.rstrip("/") + "/"
        with get_db_session() as session:
            result = VendorDocIngestService(
                session,
                official_domains={package_name: [hostname]},
            ).discover_and_ingest(
                package_name=package_name,
                ecosystem=ecosystem,
                requests=[
                    VendorDocDiscoveryRequest(
                        index_url=index_url,
                        doc_type="release_notes",
                        version_range=version_range,
                        include_url_prefixes=[base_prefix],
                        include_doc_types=["release_notes", "migration_guide"],
                        max_pages=10,
                    )
                ],
            )
        print(result)
        return
    if len(sys.argv) >= 4 and sys.argv[1:3] == ["eval", "run"]:
        args = sys.argv[3:]
        dataset_path = Path(args[0])
        baseline_dataset_name = _parse_flag_value(args[1:], "--baseline-dataset-name")
        candidate_profiles = _parse_csv_flag(args[1:], "--candidate-profiles")
        rerank_profiles = _parse_csv_flag(args[1:], "--rerank-profiles")
        with get_db_session() as session:
            runner = EvalRunnerService(session)
            if candidate_profiles or rerank_profiles:
                runner_settings = runner.tool_service.search_service.settings
                result = runner.run_profile_matrix(
                    dataset_path=dataset_path,
                    candidate_profiles=candidate_profiles
                    or [runner_settings.retrieval_candidate_profile],
                    rerank_profiles=rerank_profiles
                    or [runner_settings.retrieval_rerank_profile],
                    baseline_dataset_name=baseline_dataset_name,
                )
            else:
                result = runner.run_from_yaml(
                    dataset_path,
                    baseline_dataset_name=baseline_dataset_name,
                )
        print(result)
        return
    print(f"{settings.app_name} [{settings.env}]")
