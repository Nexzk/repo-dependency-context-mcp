from __future__ import annotations

import json
import re
import tomllib
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from repo_dependency_context_mcp.db.models import Dependency


@dataclass(slots=True)
class DependencyParseSummary:
    count: int


class DependencyParserService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def parse_and_persist(self, tenant_id: uuid.UUID, repo_id: uuid.UUID, repo_path: Path) -> DependencyParseSummary:
        dependencies = [
            *self._parse_requirements(repo_path / "requirements.txt"),
            *self._parse_pyproject(repo_path / "pyproject.toml"),
            *self._parse_package_json(repo_path / "package.json"),
        ]

        deduped: dict[tuple[str, str], dict] = {}
        for item in dependencies:
            deduped[(item["ecosystem"], item["package_name"])] = item

        self.session.execute(delete(Dependency).where(Dependency.repo_id == repo_id))
        for item in deduped.values():
            self.session.add(
                Dependency(
                    tenant_id=tenant_id,
                    repo_id=repo_id,
                    package_name=item["package_name"],
                    ecosystem=item["ecosystem"],
                    declared_version=item["declared_version"],
                    resolved_version=item.get("resolved_version"),
                    manager=item["manager"],
                    metadata_json=item.get("metadata", {}),
                )
            )

        self.session.commit()
        return DependencyParseSummary(count=len(deduped))

    def _parse_requirements(self, path: Path) -> list[dict]:
        if not path.exists():
            return []

        dependencies: list[dict] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            name, version = _split_python_requirement(stripped)
            dependencies.append(
                {
                    "package_name": name,
                    "ecosystem": "python",
                    "declared_version": version,
                    "resolved_version": None,
                    "manager": "pip",
                    "metadata": {"source_file": "requirements.txt"},
                }
            )
        return dependencies

    def _parse_pyproject(self, path: Path) -> list[dict]:
        if not path.exists():
            return []

        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        project = payload.get("project", {})
        entries = project.get("dependencies", [])
        dependencies: list[dict] = []
        for entry in entries:
            name, version = _split_python_requirement(entry)
            dependencies.append(
                {
                    "package_name": name,
                    "ecosystem": "python",
                    "declared_version": version,
                    "resolved_version": None,
                    "manager": "pip",
                    "metadata": {"source_file": "pyproject.toml"},
                }
            )
        return dependencies

    def _parse_package_json(self, path: Path) -> list[dict]:
        if not path.exists():
            return []

        payload = json.loads(path.read_text(encoding="utf-8"))
        sections = {
            "dependencies": payload.get("dependencies", {}),
            "devDependencies": payload.get("devDependencies", {}),
        }
        dependencies: list[dict] = []
        for section_name, items in sections.items():
            for package_name, version in items.items():
                dependencies.append(
                    {
                        "package_name": package_name,
                        "ecosystem": "node",
                        "declared_version": str(version),
                        "resolved_version": None,
                        "manager": "npm",
                        "metadata": {"source_file": "package.json", "section": section_name},
                    }
                )
        return dependencies


_PYTHON_REQ_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)\s*(.*)$")


def _split_python_requirement(entry: str) -> tuple[str, str]:
    match = _PYTHON_REQ_PATTERN.match(entry.strip())
    if not match:
        return entry.strip(), ""
    name = match.group(1)
    version = match.group(2).strip() or "*"
    return name, version
