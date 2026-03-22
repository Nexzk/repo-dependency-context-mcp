from pathlib import Path

from sqlalchemy import select

from repo_dependency_context_mcp.db.models import Dependency, Repo, Tenant
from repo_dependency_context_mcp.services.dependencies.parser import DependencyParserService


def test_dependency_parser_extracts_python_and_node_dependencies(db_session, tmp_path: Path) -> None:
    repo_root = tmp_path / "deps_repo"
    repo_root.mkdir()

    (repo_root / "requirements.txt").write_text(
        "\n".join(
            [
                "fastapi==0.115.0",
                "sqlalchemy>=2.0,<3.0",
            ]
        ),
        encoding="utf-8",
    )
    (repo_root / "package.json").write_text(
        """{
  "name": "demo-web",
  "dependencies": {
    "react": "^18.3.0",
    "antd": "^6.0.0"
  }
}""",
        encoding="utf-8",
    )

    tenant = Tenant(name="Tenant Deps", slug="tenant-deps")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="deps-repo",
        provider="local",
        external_id="deps-repo",
        default_branch="main",
        acl_scope={"visibility": "private"},
    )
    db_session.add(repo)
    db_session.commit()

    summary = DependencyParserService(db_session).parse_and_persist(
        tenant_id=tenant.id,
        repo_id=repo.id,
        repo_path=repo_root,
    )

    assert summary.count == 4

    dependencies = db_session.scalars(
        select(Dependency).order_by(Dependency.ecosystem, Dependency.package_name)
    ).all()
    assert [(dep.ecosystem, dep.package_name, dep.manager) for dep in dependencies] == [
        ("node", "antd", "npm"),
        ("node", "react", "npm"),
        ("python", "fastapi", "pip"),
        ("python", "sqlalchemy", "pip"),
    ]
