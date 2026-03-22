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
                requests=[VendorDocFetchRequest(doc_type="release_notes", url=url, version_range=version_range)],
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
        with get_db_session() as session:
            result = EvalRunnerService(session).run_from_yaml(Path(sys.argv[3]))
        print(result)
        return
    print(f"{settings.app_name} [{settings.env}]")
