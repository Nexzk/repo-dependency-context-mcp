from __future__ import annotations

import uuid
from typing import Any, Callable

import httpx
from sqlalchemy.orm import Session

from repo_dependency_context_mcp.services.ingest.change_metadata import ChangeMetadataIngestService
from repo_dependency_context_mcp.services.ingest.sync_state import SyncStateService


class GitHubMetadataIngestService:
    def __init__(
        self,
        session: Session,
        base_url: str = "https://api.github.com",
        token: str | None = None,
    ) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.token = token

    def ingest_repo_changes(
        self,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID,
        owner: str,
        repo_name: str,
        acl_scope: dict[str, Any],
    ) -> int:
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        with httpx.Client(base_url=self.base_url, headers=headers, timeout=10.0) as client:
            scope_base = f"{owner}/{repo_name}"
            total = 0
            total += self._ingest_resource(
                client=client,
                tenant_id=tenant_id,
                repo_id=repo_id,
                acl_scope=acl_scope,
                source_kind="github_prs",
                scope_key=f"{scope_base}:pulls",
                cursor_kind="updated_at",
                path=f"/repos/{owner}/{repo_name}/pulls",
                normalize=self._normalize_pull,
                timestamp_key="source_updated_at",
                predicate=None,
            )
            total += self._ingest_resource(
                client=client,
                tenant_id=tenant_id,
                repo_id=repo_id,
                acl_scope=acl_scope,
                source_kind="github_issues",
                scope_key=f"{scope_base}:issues",
                cursor_kind="updated_at",
                path=f"/repos/{owner}/{repo_name}/issues",
                normalize=self._normalize_issue,
                timestamp_key="source_updated_at",
                predicate=lambda item: not item.get("pull_request"),
            )
            total += self._ingest_resource(
                client=client,
                tenant_id=tenant_id,
                repo_id=repo_id,
                acl_scope=acl_scope,
                source_kind="github_commits",
                scope_key=f"{scope_base}:commits",
                cursor_kind="committed_at",
                path=f"/repos/{owner}/{repo_name}/commits",
                normalize=self._normalize_commit,
                timestamp_key="source_updated_at",
                predicate=None,
            )
            return total

    def _ingest_resource(
        self,
        client: httpx.Client,
        tenant_id: uuid.UUID,
        repo_id: uuid.UUID,
        acl_scope: dict[str, Any],
        source_kind: str,
        scope_key: str,
        cursor_kind: str,
        path: str,
        normalize: Callable[[dict[str, Any]], dict[str, Any]],
        timestamp_key: str,
        predicate: Callable[[dict[str, Any]], bool] | None,
    ) -> int:
        sync_state = SyncStateService(self.session)
        run = sync_state.start_run(
            tenant_id=tenant_id,
            repo_id=repo_id,
            source_kind=source_kind,
            scope_key=scope_key,
            cursor_kind=cursor_kind,
        )
        cursor_before = run.cursor_before

        try:
            response = client.get(path)
            response.raise_for_status()
            payload = response.json()
            if predicate is None:
                filtered_items = payload
            else:
                filtered_items = [item for item in payload if predicate(item)]
            normalized_items = [normalize(item) for item in filtered_items]
            incremental_items = [
                item
                for item in normalized_items
                if self._is_newer_than_cursor(item.get(timestamp_key), cursor_before)
            ]
            written = ChangeMetadataIngestService(self.session).ingest_items(
                tenant_id=tenant_id,
                repo_id=repo_id,
                items=incremental_items,
                acl_scope=acl_scope,
            )
            cursor_after = self._max_cursor_value(
                [item.get(timestamp_key) for item in incremental_items],
                cursor_before,
            )
            sync_state.mark_success(
                run=run,
                cursor_after=cursor_after,
                items_seen=len(filtered_items),
                items_written=written,
            )
            return written
        except Exception as exc:
            sync_state.mark_failure(run=run, error=str(exc))
            raise

    def _normalize_pull(self, item: dict[str, Any]) -> dict[str, Any]:
        title = item["title"]
        body = item.get("body") or ""
        related = _extract_related_metadata(f"{title}\n{body}")
        return {
            "source_type": "pr",
            "external_ref": f"pr-{item['number']}",
            "source_pr_ref": f"pr-{item['number']}",
            "title": title,
            "body": body,
            "author": item.get("user", {}).get("login"),
            "labels": [label["name"] for label in item.get("labels", [])],
            "source_updated_at": item.get("updated_at"),
            "merged_at": item.get("merged_at"),
            **related,
        }

    def _normalize_issue(self, item: dict[str, Any]) -> dict[str, Any]:
        title = item["title"]
        body = item.get("body") or ""
        related = _extract_related_metadata(f"{title}\n{body}")
        return {
            "source_type": "issue",
            "external_ref": f"issue-{item['number']}",
            "source_issue_ref": f"issue-{item['number']}",
            "title": title,
            "body": body,
            "author": item.get("user", {}).get("login"),
            "labels": [label["name"] for label in item.get("labels", [])],
            "source_updated_at": item.get("updated_at"),
            "merged_at": None,
            **related,
        }

    def _normalize_commit(self, item: dict[str, Any]) -> dict[str, Any]:
        message = item.get("commit", {}).get("message", "")
        related = _extract_related_metadata(message)
        return {
            "source_type": "commit",
            "external_ref": item["sha"],
            "source_commit_sha": item["sha"],
            "source_commit_ref": item["sha"],
            "title": message.splitlines()[0] if message else item["sha"],
            "body": "\n".join(message.splitlines()[1:]).strip(),
            "author": item.get("commit", {}).get("author", {}).get("name"),
            "labels": [],
            "source_updated_at": item.get("commit", {}).get("author", {}).get("date"),
            "merged_at": None,
            **related,
        }

    def _is_newer_than_cursor(self, candidate: str | None, cursor_before: str | None) -> bool:
        if candidate is None:
            return True
        if cursor_before is None:
            return True
        return candidate > cursor_before

    def _max_cursor_value(
        self,
        candidates: list[str | None],
        cursor_before: str | None,
    ) -> str | None:
        values = [candidate for candidate in candidates if candidate is not None]
        if not values:
            return cursor_before
        return max(values)


def _extract_related_metadata(text: str) -> dict[str, list[str]]:
    file_paths: list[str] = []
    symbols: list[str] = []
    for token in text.replace(",", " ").split():
        normalized = token.strip("()[]{}:;.")
        if "/" in normalized or "." in normalized:
            file_paths.append(normalized)
        elif "_" in normalized:
            symbols.append(normalized)
    return {
        "related_paths": sorted(set([*file_paths, *symbols])),
        "related_file_paths": sorted(set(file_paths)),
        "related_symbols": sorted(set(symbols)),
    }
