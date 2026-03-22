from sqlalchemy import select

from repo_dependency_context_mcp.db.models import DependencyDoc
from repo_dependency_context_mcp.services.dependencies.vendor_docs import (
    VendorDocCandidate,
    VendorDocIngestService,
)


def test_vendor_doc_ingest_enforces_official_domain_whitelist(db_session, settings) -> None:
    service = VendorDocIngestService(
        db_session,
        official_domains={
            "fastapi": ["fastapi.tiangolo.com"],
            "react": ["react.dev"],
        },
    )

    accepted = service.ingest_candidates(
        package_name="fastapi",
        ecosystem="python",
        candidates=[
            VendorDocCandidate(
                doc_type="migration_guide",
                authority="official",
                url="https://fastapi.tiangolo.com/release-notes/",
                title="FastAPI Release Notes",
                section_title="0.115",
                raw_text="Official release notes",
                version_range="0.115.x",
            ),
            VendorDocCandidate(
                doc_type="changelog",
                authority="community",
                url="https://example.com/fastapi-upgrade",
                title="Community FastAPI Upgrade Notes",
                section_title=None,
                raw_text="Should be rejected",
                version_range="0.115.x",
            ),
        ],
    )

    assert accepted == 1

    docs = db_session.scalars(select(DependencyDoc)).all()
    assert len(docs) == 1
    assert docs[0].url == "https://fastapi.tiangolo.com/release-notes/"
