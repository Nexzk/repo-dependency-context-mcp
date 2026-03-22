from __future__ import annotations

import uuid

import httpx
from sqlalchemy.orm import Session

from repo_dependency_context_mcp.services.ingest.change_metadata import ChangeMetadataIngestService


class GitHubMetadataIngestService:
    def __init__(self, session: Session, base_url: str = "https://api.github.com", token: str | None = None) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.token = token

    def ingest_repo_changes(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID,
        owner: str,
        repo_name: str,
        acl_scope: dict,
    ) -> int:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        with httpx.Client(base_url=self.base_url, headers=headers, timeout=10.0) as client:
            pulls = client.get(f"/repos/{owner}/{repo_name}/pulls").json()
            issues = client.get(f"/repos/{owner}/{repo_name}/issues").json()
            commits = client.get(f"/repos/{owner}/{repo_name}/commits").json()

        items = [
            *[self._normalize_pull(item) for item in pulls],
            *[self._normalize_issue(item) for item in issues if not item.get("pull_request")],
            *[self._normalize_commit(item) for item in commits],
        ]

        return ChangeMetadataIngestService(self.session).ingest_items(
            tenant_id=tenant_id,
            repo_id=repo_id,
            items=items,
            acl_scope=acl_scope,
        )

    def _normalize_pull(self, item: dict) -> dict:
        title = item["title"]
        body = item.get("body") or ""
        related = _extract_related_paths(f"{title}\n{body}")
        return {
            "source_type": "pr",
            "external_ref": f"pr-{item['number']}",
            "title": title,
            "body": body,
            "author": item.get("user", {}).get("login"),
            "labels": [label["name"] for label in item.get("labels", [])],
            "merged_at": item.get("merged_at"),
            "related_paths": related,
        }

    def _normalize_issue(self, item: dict) -> dict:
        title = item["title"]
        body = item.get("body") or ""
        related = _extract_related_paths(f"{title}\n{body}")
        return {
            "source_type": "issue",
            "external_ref": f"issue-{item['number']}",
            "title": title,
            "body": body,
            "author": item.get("user", {}).get("login"),
            "labels": [label["name"] for label in item.get("labels", [])],
            "merged_at": None,
            "related_paths": related,
        }

    def _normalize_commit(self, item: dict) -> dict:
        message = item.get("commit", {}).get("message", "")
        related = _extract_related_paths(message)
        return {
            "source_type": "commit",
            "external_ref": item["sha"],
            "title": message.splitlines()[0] if message else item["sha"],
            "body": "\n".join(message.splitlines()[1:]).strip(),
            "author": item.get("commit", {}).get("author", {}).get("name"),
            "labels": [],
            "merged_at": None,
            "related_paths": related,
        }


def _extract_related_paths(text: str) -> list[str]:
    candidates: list[str] = []
    for token in text.replace(",", " ").split():
        normalized = token.strip("()[]{}:;.")
        if "/" in normalized or "_" in normalized:
            candidates.append(normalized)
    return sorted(set(candidates))
