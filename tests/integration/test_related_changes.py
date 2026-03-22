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
    assert result["pull_requests"][0]["related_file_paths"] == ["src/auth.py"]
    assert result["pull_requests"][0]["related_symbols"] == ["require_admin"]
    assert result["pull_requests"][0]["source_pr_ref"] == "pr-101"
    assert result["commits"][0]["source_commit_sha"] == "abc123"
    assert result["issues"][0]["source_issue_ref"] == "issue-77"


def test_get_related_changes_ranks_path_before_symbol_before_combined_before_lexical(
    db_session,
    tmp_path: Path,
) -> None:
    tenant = Tenant(name="Tenant Ranked Changes", slug="tenant-ranked-changes")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="ranked-repo",
        provider="local",
        external_id="ranked-repo",
        default_branch="main",
        acl_scope={"visibility": "private"},
    )
    db_session.add(repo)
    db_session.commit()

    fixture_path = tmp_path / "changes_ranked.json"
    fixture_path.write_text(
        """
[
  {
    "source_type": "pr",
    "external_ref": "pr-path",
    "title": "Patch auth file handling",
    "body": "Touches exact file path only.",
    "author": "alice",
    "merged_at": "2026-03-01T00:00:00Z",
    "related_paths": ["src/auth.py"]
  },
  {
    "source_type": "pr",
    "external_ref": "pr-symbol",
    "title": "Adjust require_admin behavior",
    "body": "Touches exact symbol only.",
    "author": "bob",
    "merged_at": "2026-03-15T00:00:00Z",
    "related_paths": ["require_admin"]
  },
  {
    "source_type": "pr",
    "external_ref": "pr-both",
    "title": "Update auth path and symbol",
    "body": "Touches both exact path and symbol.",
    "author": "carol",
    "merged_at": "2026-03-20T00:00:00Z",
    "related_paths": ["src/auth.py", "require_admin"]
  },
  {
    "source_type": "pr",
    "external_ref": "pr-lexical",
    "title": "Investigate admin authorization",
    "body": "Mentions src auth and admin guard in text only.",
    "author": "dave",
    "merged_at": "2026-03-21T00:00:00Z",
    "related_paths": []
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

    refs = [item["external_ref"] for item in result["pull_requests"]]
    assert refs == ["pr-path", "pr-symbol", "pr-both", "pr-lexical"]


def test_get_related_changes_uses_freshness_as_tiebreaker_for_same_match_strength(
    db_session,
    tmp_path: Path,
) -> None:
    tenant = Tenant(name="Tenant Fresh Changes", slug="tenant-fresh-changes")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="fresh-repo",
        provider="local",
        external_id="fresh-repo",
        default_branch="main",
        acl_scope={"visibility": "private"},
    )
    db_session.add(repo)
    db_session.commit()

    fixture_path = tmp_path / "changes_fresh.json"
    fixture_path.write_text(
        """
[
  {
    "source_type": "commit",
    "external_ref": "commit-old",
    "title": "Older require_admin update",
    "body": "Symbol-only reference.",
    "author": "alice",
    "merged_at": "2026-03-01T00:00:00Z",
    "related_paths": ["require_admin"]
  },
  {
    "source_type": "commit",
    "external_ref": "commit-new",
    "title": "Newer require_admin update",
    "body": "Symbol-only reference.",
    "author": "bob",
    "merged_at": "2026-03-21T00:00:00Z",
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

    refs = [item["external_ref"] for item in result["commits"]]
    assert refs == ["commit-new", "commit-old"]


def test_get_related_changes_prefers_explicit_related_metadata_fields(db_session, tmp_path: Path) -> None:
    tenant = Tenant(name="Tenant Explicit Metadata", slug="tenant-explicit-metadata")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="explicit-repo",
        provider="local",
        external_id="explicit-repo",
        default_branch="main",
        acl_scope={"visibility": "private"},
    )
    db_session.add(repo)
    db_session.commit()

    fixture_path = tmp_path / "changes_explicit.json"
    fixture_path.write_text(
        """
[
  {
    "source_type": "issue",
    "external_ref": "issue-file-only",
    "title": "File path specific regression",
    "body": "Regression in auth flow.",
    "author": "alice",
    "related_file_paths": ["src/auth.py"],
    "related_symbols": []
  },
  {
    "source_type": "issue",
    "external_ref": "issue-symbol-only",
    "title": "Symbol specific regression",
    "body": "Regression in guard flow.",
    "author": "bob",
    "related_file_paths": [],
    "related_symbols": ["require_admin"]
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

    refs = [item["external_ref"] for item in result["issues"]]
    assert refs == ["issue-file-only", "issue-symbol-only"]
