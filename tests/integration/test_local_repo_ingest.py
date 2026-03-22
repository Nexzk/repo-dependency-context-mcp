from pathlib import Path

from sqlalchemy import select

from repo_dependency_context_mcp.db.models import (
    Chunk,
    Document,
    Repo,
    Source,
    SyncCursor,
    SyncRun,
    Tenant,
)
from repo_dependency_context_mcp.services.ingest.local_repo import LocalRepoIngestService


def test_local_repo_ingest_persists_code_and_markdown_chunks(db_session, tmp_path: Path) -> None:
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
                "",
                "def allow_anyone(user):",
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

    tenant = Tenant(name="Tenant One", slug="tenant-one")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="sample-repo",
        provider="local",
        external_id="sample-repo",
        default_branch="main",
        acl_scope={"visibility": "private"},
    )
    db_session.add(repo)
    db_session.commit()

    service = LocalRepoIngestService(db_session)

    result = service.ingest_repo(
        tenant_id=tenant.id,
        repo_id=repo.id,
        repo_path=repo_root,
        acl_scope={"visibility": "private"},
    )

    assert result.source_count == 2
    assert result.document_count == 2
    assert result.chunk_count >= 3

    sources = db_session.scalars(
        select(Source).order_by(Source.source_type, Source.path_or_url)
    ).all()
    assert [source.source_type for source in sources] == ["repo_code", "repo_doc"]

    documents = db_session.scalars(select(Document).order_by(Document.title)).all()
    assert len(documents) == 2
    assert {document.mime_type for document in documents} == {"text/markdown", "text/x-python"}

    chunks = db_session.scalars(select(Chunk).order_by(Chunk.chunk_type, Chunk.chunk_index)).all()
    assert any("Repo: sample-repo" in chunk.context_prefix for chunk in chunks)
    assert any("File: src/auth.py" in chunk.context_prefix for chunk in chunks)
    assert any("Symbol: require_admin" in chunk.context_prefix for chunk in chunks)
    assert any("Section: Authentication > Admin Routes" in chunk.context_prefix for chunk in chunks)
    assert all(chunk.authority == "repo" for chunk in chunks)
    assert all(chunk.acl_scope == {"visibility": "private"} for chunk in chunks)

    cursor = db_session.scalar(
        select(SyncCursor).where(
            SyncCursor.repo_id == repo.id,
            SyncCursor.source_kind == "local_repo",
        )
    )
    run = db_session.scalar(
        select(SyncRun).where(
            SyncRun.repo_id == repo.id,
            SyncRun.source_kind == "local_repo",
        )
    )
    assert cursor is not None
    assert cursor.cursor_kind == "repo_snapshot"
    assert cursor.cursor_value is not None
    assert cursor.last_success_at is not None
    assert run is not None
    assert run.status == "completed"
    assert run.items_seen == 2
    assert run.items_written == 2
