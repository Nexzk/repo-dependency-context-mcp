from pathlib import Path

from repo_dependency_context_mcp.db.models import Repo, Tenant
from repo_dependency_context_mcp.services.ingest.change_metadata import ChangeMetadataIngestService
from repo_dependency_context_mcp.services.ingest.local_repo import LocalRepoIngestService
from repo_dependency_context_mcp.services.mcp.tools import MCPToolService


def test_get_related_changes_returns_pr_commit_and_issue_summaries(db_session, tmp_path: Path) -> None:
    repo_root = tmp_path / "sample_repo"
    repo_root.mkdir()
    (repo_root / "src").mkdir()
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

    tenant = Tenant(name="Tenant Changes", slug="tenant-changes")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo",
        provider="local",
        external_id="sample-repo-changes",
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

    fixture_path = tmp_path / "changes.json"
    fixture_path.write_text(
        """
[
  {
    "source_type": "pr",
    "external_ref": "pr-101",
    "title": "Harden admin middleware",
    "body": "Updates require_admin and related auth checks.",
    "author": "alice",
    "labels": ["auth", "security"],
    "merged_at": "2026-03-20T00:00:00Z",
    "related_paths": ["src/auth.py", "require_admin"]
  },
  {
    "source_type": "commit",
    "external_ref": "abc123",
    "title": "Refine require_admin guard",
    "body": "Adjusts admin authorization logic in src/auth.py.",
    "author": "bob",
    "related_paths": ["src/auth.py", "require_admin"]
  },
  {
    "source_type": "issue",
    "external_ref": "issue-77",
    "title": "Admin route fails for privileged users",
    "body": "Possible regression around require_admin.",
    "author": "carol",
    "labels": ["bug"],
    "related_paths": ["require_admin"]
  }
]
""".strip(),
        encoding="utf-8",
    )

    ChangeMetadataIngestService(db_session).ingest_json_fixture(
        tenant_id=tenant.id,
        repo_id=repo.id,
        fixture_path=fixture_path,
        acl_scope={"visibility": "private"},
    )

    result = MCPToolService(db_session).get_related_changes(
        tenant_id=tenant.id,
        repo_id=repo.id,
        path_or_symbol="src/auth.py:require_admin",
        since_days=90,
    )

    assert len(result["pull_requests"]) == 1
    assert len(result["commits"]) == 1
    assert len(result["issues"]) == 1
    assert result["pull_requests"][0]["title"] == "Harden admin middleware"
    assert result["commits"][0]["external_ref"] == "abc123"
    assert result["issues"][0]["title"] == "Admin route fails for privileged users"
