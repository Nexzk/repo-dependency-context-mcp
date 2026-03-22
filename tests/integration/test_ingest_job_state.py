from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from repo_dependency_context_mcp.db.models import IngestJob, Repo, Tenant
from repo_dependency_context_mcp.services.ingest.local_repo import LocalRepoIngestService


def test_local_repo_ingest_records_completed_job_state(db_session, tmp_path: Path) -> None:
    tenant = Tenant(name="Tenant Job State", slug="tenant-job-state")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="job-state-repo",
        provider="github",
        external_id="acme/job-state",
        default_branch="main",
        acl_scope={"visibility": "private"},
    )
    db_session.add(repo)
    db_session.commit()

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src").mkdir()
    (repo_root / "src" / "auth.py").write_text(
        "def require_admin(user):\n    return user.get('is_admin', False)\n",
        encoding="utf-8",
    )

    LocalRepoIngestService(db_session).ingest_repo(
        tenant_id=tenant.id,
        repo_id=repo.id,
        repo_path=repo_root,
        acl_scope={"visibility": "private"},
    )

    job = db_session.execute(select(IngestJob).order_by(IngestJob.created_at.desc())).scalar_one()
    assert job.status == "completed"
    assert job.failure_count == 0
    assert job.started_at is not None
    assert job.finished_at is not None
    assert job.finished_at >= job.started_at


def test_local_repo_ingest_records_failed_job_state(db_session, tmp_path: Path) -> None:
    tenant = Tenant(name="Tenant Job Failure", slug="tenant-job-failure")
    db_session.add(tenant)
    db_session.flush()

    repo = Repo(
        tenant_id=tenant.id,
        name="job-failure-repo",
        provider="github",
        external_id="acme/job-failure",
        default_branch="main",
        acl_scope={"visibility": "private"},
    )
    db_session.add(repo)
    db_session.commit()

    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "src").mkdir()
    (repo_root / "src" / "bad.py").write_bytes(b"\xff\xfe\x00")

    with pytest.raises(UnicodeDecodeError):
        LocalRepoIngestService(db_session).ingest_repo(
            tenant_id=tenant.id,
            repo_id=repo.id,
            repo_path=repo_root,
            acl_scope={"visibility": "private"},
        )

    job = db_session.execute(select(IngestJob).order_by(IngestJob.created_at.desc())).scalar_one()
    assert job.status == "failed"
    assert job.failure_count == 1
    assert job.started_at is not None
    assert job.finished_at is not None
    assert job.finished_at >= job.started_at
