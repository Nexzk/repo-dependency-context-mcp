from pathlib import Path

from sqlalchemy import select

from repo_dependency_context_mcp.db.models import QueryLog, QueryResult, Repo, Tenant
from repo_dependency_context_mcp.services.ingest.local_repo import LocalRepoIngestService
from repo_dependency_context_mcp.services.retrieval.search import SearchContextService


def test_search_context_returns_evidence_and_persists_query_audit(db_session, tmp_path: Path) -> None:
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

    tenant = Tenant(name="Tenant Search", slug="tenant-search")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo",
        provider="local",
        external_id="sample-repo-search",
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

    response = SearchContextService(db_session).search_context(
        tenant_id=tenant.id,
        repo_id=repo.id,
        query="where is admin authorization logic",
        task_type="locate",
        top_k=3,
    )

    assert response["task_type"] == "locate"
    assert response["clarify_needed"] is False
    assert response["conflicts"] == []
    assert response["gaps"] == []
    assert len(response["evidence"]) >= 1
    assert response["evidence"][0]["authority"] == "repo"
    assert response["evidence"][0]["why_selected"]
    assert response["evidence"][0]["freshness_reason"]
    assert "require_admin" in response["evidence"][0]["snippet"]

    query_log = db_session.scalar(select(QueryLog))
    assert query_log is not None
    assert query_log.query_text == "where is admin authorization logic"
    assert query_log.result_count == len(response["evidence"])

    query_results = db_session.scalars(select(QueryResult).order_by(QueryResult.rank)).all()
    assert len(query_results) == len(response["evidence"])
    assert all(result.evidence_payload for result in query_results)
    assert all(result.why_selected for result in query_results)
