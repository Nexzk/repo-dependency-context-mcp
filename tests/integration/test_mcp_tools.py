from pathlib import Path

from repo_dependency_context_mcp.db.models import Repo, Tenant
from repo_dependency_context_mcp.services.dependencies.parser import DependencyParserService
from repo_dependency_context_mcp.services.dependencies.vendor_docs import (
    VendorDocCandidate,
    VendorDocIngestService,
)
from repo_dependency_context_mcp.services.ingest.local_repo import LocalRepoIngestService
from repo_dependency_context_mcp.services.mcp.tools import MCPToolService


def test_mcp_tools_return_structured_results(db_session, tmp_path: Path) -> None:
    repo_root = tmp_path / "sample_repo"
    repo_root.mkdir()
    (repo_root / "src").mkdir()
    (repo_root / "docs").mkdir()

    (repo_root / "src" / "auth.py").write_text(
        "\n".join(
            [
                "def require_admin(user):",
                "    if not user.get('is_admin'):",
                "        raise PermissionError('admin only')",
                "    return True",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "docs" / "auth.md").write_text(
        "\n".join(
            [
                "# Authentication",
                "",
                "## Admin Routes",
                "",
                "Admin routes require the require_admin helper.",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "docs" / "fastapi-upgrade-notes.md").write_text(
        "\n".join(
            [
                "# FastAPI Upgrade Notes",
                "",
                "Internal migration note for FastAPI.",
                "This older internal note still references pre-0.115 migration guidance.",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "requirements.txt").write_text(
        "fastapi==0.115.0\n",
        encoding="utf-8",
    )

    tenant = Tenant(name="Tenant MCP", slug="tenant-mcp")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo",
        provider="local",
        external_id="sample-repo-mcp",
        default_branch="main",
        acl_scope={"visibility": "private"},
    )
    db_session.add(repo)
    db_session.commit()

    LocalRepoIngestService(db_session).ingest_repo(
        tenant_id=tenant.id,
        repo_id=repo.id,
        repo_path=repo_root,
        acl_scope={"visibility": "private"},
    )
    DependencyParserService(db_session).parse_and_persist(
        tenant_id=tenant.id,
        repo_id=repo.id,
        repo_path=repo_root,
    )
    VendorDocIngestService(
        db_session,
        official_domains={"fastapi": ["fastapi.tiangolo.com"]},
    ).ingest_candidates(
        package_name="fastapi",
        ecosystem="python",
        candidates=[
            VendorDocCandidate(
                doc_type="migration_guide",
                authority="official",
                url="https://fastapi.tiangolo.com/release-notes/",
                title="FastAPI Release Notes",
                section_title="0.115",
                raw_text="Dependency migration notes for FastAPI.",
                version_range="0.115.x",
            )
        ],
    )

    service = MCPToolService(db_session)

    search_result = service.search_context(
        tenant_id=tenant.id,
        repo_id=repo.id,
        query="where is admin authorization logic",
        task_type="locate",
        top_k=3,
    )
    assert search_result["evidence"]
    assert search_result["evidence"][0]["why_selected"]

    source_result = service.get_source(
        tenant_id=tenant.id,
        repo_id=repo.id,
        path_or_url="src/auth.py",
        start_line=1,
        end_line=4,
    )
    assert source_result["path_or_url"] == "src/auth.py"
    assert "require_admin" in source_result["content"]

    related_changes = service.get_related_changes(
        tenant_id=tenant.id,
        repo_id=repo.id,
        path_or_symbol="src/auth.py:require_admin",
        since_days=90,
    )
    assert related_changes == {"pull_requests": [], "commits": [], "issues": []}

    dependency_notes = service.get_dependency_notes(
        tenant_id=tenant.id,
        repo_id=repo.id,
        package_name="fastapi",
        version_range="0.115.x",
        topic="migration",
    )
    assert len(dependency_notes["evidence"]) == 3
    assert dependency_notes["evidence"][0]["authority"] == "official"
    assert dependency_notes["evidence"][1]["source_type"] == "repo_doc"
    assert dependency_notes["evidence"][1]["path_or_url"] == "docs/fastapi-upgrade-notes.md"
    assert dependency_notes["evidence"][2]["authority"] == "repo"
    assert dependency_notes["evidence"][2]["path_or_url"] == "requirements.txt"


def test_dependency_notes_prefers_vendor_doc_sections(db_session) -> None:
    tenant = Tenant(name="Tenant Vendor Docs", slug="tenant-vendor-docs")
    db_session.add(tenant)
    db_session.commit()

    service = VendorDocIngestService(
        db_session,
        official_domains={"fastapi": ["fastapi.tiangolo.com"]},
    )
    service.ingest_candidates(
        package_name="fastapi",
        ecosystem="python",
        candidates=[
            VendorDocCandidate(
                doc_type="migration_guide",
                authority="official",
                url="https://fastapi.tiangolo.com/release-notes/",
                title="FastAPI Release Notes",
                section_title="0.115",
                raw_text=(
                    "FastAPI Release Notes\n"
                    "0.115\nMigration details for FastAPI 0.115.\n"
                    "0.116\nMigration details for FastAPI 0.116."
                ),
                version_range=">=0.115,<0.117",
                metadata_json={
                    "structure_kind": "versioned_sections",
                    "version_headings": ["0.115", "0.116"],
                    "sections": [
                        {
                            "section_title": "0.115",
                            "heading": "0.115",
                            "raw_text": "Migration details for FastAPI 0.115.",
                            "section_index": 0,
                        },
                        {
                            "section_title": "0.116",
                            "heading": "0.116",
                            "raw_text": "Migration details for FastAPI 0.116.",
                            "section_index": 1,
                        },
                    ],
                },
            )
        ],
    )

    tool_service = MCPToolService(db_session)
    dependency_notes = tool_service.get_dependency_notes(
        tenant_id=tenant.id,
        repo_id=None,
        package_name="fastapi",
        version_range=">=0.115,<0.117",
        topic="migration",
    )

    vendor_evidence = [
        item for item in dependency_notes["evidence"] if item["source_type"] == "vendor_doc"
    ]
    assert [item["section_title"] for item in vendor_evidence] == ["0.115", "0.116"]
    assert "0.115" in vendor_evidence[0]["why_selected"]
    assert "0.116" in vendor_evidence[1]["why_selected"]
