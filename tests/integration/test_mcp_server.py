from pathlib import Path

import anyio

from repo_dependency_context_mcp.db.models import Repo, Tenant
from repo_dependency_context_mcp.services.ingest.local_repo import LocalRepoIngestService
from repo_dependency_context_mcp.services.mcp.server import build_mcp_server


def test_mcp_server_lists_tools_and_calls_search_context(db_session, tmp_path: Path) -> None:
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

    tenant = Tenant(name="Tenant MCP Server", slug="tenant-mcp-server")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo",
        provider="local",
        external_id="sample-repo-mcp-server",
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

    server = build_mcp_server(lambda: db_session)

    tools = anyio.run(server.list_tools)
    tool_names = {tool.name for tool in tools}
    assert tool_names == {
        "search_context",
        "get_source",
        "get_related_changes",
        "get_dependency_notes",
    }

    result = anyio.run(
        server.call_tool,
        "search_context",
        {
            "tenant_id": str(tenant.id),
            "repo_id": str(repo.id),
            "query": "where is admin authorization logic",
            "task_type": "locate",
            "top_k": 3,
        },
    )

    if isinstance(result, tuple):
        payload = result[1]
    elif isinstance(result, dict):
        payload = result
    else:
        payload = result[0].model_dump()["structuredContent"]

    assert payload["evidence"]
    assert payload["evidence"][0]["authority"] == "repo"
