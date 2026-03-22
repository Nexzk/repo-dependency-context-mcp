from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from repo_dependency_context_mcp.api.deps import get_db_session
from repo_dependency_context_mcp.db.models import Repo, Tenant
from repo_dependency_context_mcp.services.dependencies.parser import DependencyParserService
from repo_dependency_context_mcp.services.dependencies.vendor_docs import (
    VendorDocCandidate,
    VendorDocIngestService,
)
from repo_dependency_context_mcp.services.eval.runner import EvalRunnerService
from repo_dependency_context_mcp.services.ingest.change_metadata import ChangeMetadataIngestService
from repo_dependency_context_mcp.services.ingest.local_repo import LocalRepoIngestService

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def main() -> None:
    demo_repo_src = FIXTURES / "demo_repo"
    demo_changes = FIXTURES / "demo_changes.json"
    demo_eval_template = FIXTURES / "demo_eval.yaml"

    with get_db_session() as session:
        tenant = session.query(Tenant).filter(Tenant.slug == "demo-tenant").one_or_none()
        if tenant is None:
            tenant = Tenant(name="Demo Tenant", slug="demo-tenant")
            session.add(tenant)
            session.flush()

        repo = (
            session.query(Repo)
            .filter(Repo.tenant_id == tenant.id)
            .filter(Repo.external_id == "demo-repo")
            .one_or_none()
        )
        if repo is None:
            repo = Repo(
                tenant_id=tenant.id,
                name="demo-repo",
                provider="local",
                external_id="demo-repo",
                default_branch="main",
                acl_scope={"visibility": "private"},
            )
            session.add(repo)
            session.commit()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_repo = Path(temp_dir) / "demo_repo"
            shutil.copytree(demo_repo_src, temp_repo)
            LocalRepoIngestService(session).ingest_repo(
                tenant_id=tenant.id,
                repo_id=repo.id,
                repo_path=temp_repo,
                acl_scope={"visibility": "private"},
            )
            DependencyParserService(session).parse_and_persist(
                tenant_id=tenant.id,
                repo_id=repo.id,
                repo_path=temp_repo,
            )

        ChangeMetadataIngestService(session).ingest_json_fixture(
            tenant_id=tenant.id,
            repo_id=repo.id,
            fixture_path=demo_changes,
            acl_scope={"visibility": "private"},
        )

        VendorDocIngestService(
            session,
            official_domains={"fastapi": ["fastapi.tiangolo.com"]},
        ).ingest_candidates(
            package_name="fastapi",
            ecosystem="python",
            candidates=[
                VendorDocCandidate(
                    doc_type="release_notes",
                    authority="official",
                    url="https://fastapi.tiangolo.com/release-notes/",
                    title="FastAPI Release Notes",
                    section_title="0.115",
                    raw_text="Official migration details for FastAPI 0.115.",
                    version_range="0.115.x",
                )
            ],
        )

        eval_path = Path(tempfile.gettempdir()) / "rdcmcp-demo-eval.yaml"
        template = demo_eval_template.read_text(encoding="utf-8")
        eval_path.write_text(
            template.replace("__TENANT_ID__", str(tenant.id)).replace("__REPO_ID__", str(repo.id)),
            encoding="utf-8",
        )
        eval_summary = EvalRunnerService(session).run_from_yaml(eval_path)
        tenant_id = str(tenant.id)
        repo_id = str(repo.id)

    manifest = {
        "tenant_id": tenant_id,
        "repo_id": repo_id,
        "eval_dataset": str(eval_path),
        "eval_summary": eval_summary,
    }
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
