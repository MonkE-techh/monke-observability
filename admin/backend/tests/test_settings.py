from __future__ import annotations

from pathlib import Path

import pytest

from monke_admin.registry import load_registry, valid_app_name
from monke_admin.settings import Settings

ALL = {
    "POSTHOG_PERSONAL_API_KEY": "phx_secret",
    "POSTHOG_PROJECT_ID": "12345",
    "GOOGLE_CLIENT_ID": "cid.apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "gsecret",
    "SESSION_SECRET": "s" * 40,
    "ADMIN_EMAILS": " Person@Example.com , other@example.com ",
    "PUBLIC_URL": "https://admin.example.com/",
}


def env(monkeypatch, **values):
    for key in [*ALL, "APP_ENV", "AUTH_DISABLED", "GOOGLE_WORKSPACE_DOMAIN", "POSTHOG_APP_HOST", "APPS_FILE"]:
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_complete_environment_is_configured(monkeypatch):
    env(monkeypatch, **ALL)

    s = Settings.from_env()

    assert s.missing() == []
    assert s.admin_emails == frozenset({"person@example.com", "other@example.com"})
    assert s.posthog_app_host == "https://eu.posthog.com"
    assert s.public_url == "https://admin.example.com"


def test_missing_lists_variable_names_only(monkeypatch):
    env(monkeypatch, POSTHOG_PERSONAL_API_KEY="phx_secret")

    missing = Settings.from_env().missing()

    assert "POSTHOG_PROJECT_ID" in missing and "GOOGLE_CLIENT_ID" in missing and "ADMIN_EMAILS" in missing
    assert "POSTHOG_PERSONAL_API_KEY" not in missing
    assert all("phx_" not in m for m in missing)


def test_auth_disabled_needs_no_google_settings(monkeypatch):
    env(monkeypatch, POSTHOG_PERSONAL_API_KEY="k", POSTHOG_PROJECT_ID="1", AUTH_DISABLED="true", APP_ENV="development")

    assert Settings.from_env().missing() == []


def test_auth_disabled_is_refused_in_production(monkeypatch):
    env(monkeypatch, AUTH_DISABLED="true", APP_ENV="production")

    with pytest.raises(ValueError, match="AUTH_DISABLED"):
        Settings.from_env()


def test_short_session_secret_is_reported(monkeypatch):
    env(monkeypatch, **{**ALL, "SESSION_SECRET": "short"})

    assert Settings.from_env().missing() == ["SESSION_SECRET (at least 32 characters)"]


def test_registry_reads_apps_yaml(tmp_path: Path):
    path = tmp_path / "apps.yaml"
    path.write_text("apps:\n  - name: keyword-radar\n    uses_llm: true\n    status: planned\n", encoding="utf-8")

    (app,) = load_registry(path)

    assert (app.name, app.uses_llm, app.status) == ("keyword-radar", True, "planned")


def test_registry_rejects_invalid_app_names(tmp_path: Path):
    path = tmp_path / "apps.yaml"
    path.write_text("apps:\n  - name: Keyword Radar\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Keyword Radar"):
        load_registry(path)


def test_repo_registry_is_valid():
    apps = load_registry(Path(__file__).resolve().parents[3] / "apps.yaml")

    assert {a.name for a in apps} >= {"engagement-bot-checker", "creator-curation"}


@pytest.mark.parametrize(
    ("name", "ok"), [("radar", True), ("a-b-1", True), ("A", False), ("a--b", False), ("x'y", False)]
)
def test_valid_app_name(name, ok):
    assert valid_app_name(name) is ok
