from repo_dependency_context_mcp.config import Settings


def test_settings_load_official_vendor_domains_from_env(monkeypatch) -> None:
    monkeypatch.setenv("RDCMCP_VENDOR_OFFICIAL_DOMAINS", "docs.python.org,fastapi.tiangolo.com,docs.sqlalchemy.org")

    settings = Settings()

    assert settings.vendor_official_domains == [
        "docs.python.org",
        "fastapi.tiangolo.com",
        "docs.sqlalchemy.org",
    ]
    assert settings.default_top_k == 5
    assert settings.app_name == "repo-dependency-context-mcp"
