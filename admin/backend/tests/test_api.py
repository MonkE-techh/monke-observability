from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from monke_admin.main import create_app
from monke_admin.posthog import QueryError
from monke_admin.settings import Settings


class FakeClient:
    def __init__(self, fail: bool = False):
        self.calls: list[str] = []
        self.fail = fail

    async def run(self, sql: str, *, name: str):
        self.calls.append(name)
        if self.fail:
            raise QueryError("posthog_unavailable")
        return []


@pytest.fixture
def apps_file(tmp_path: Path) -> Path:
    path = tmp_path / "apps.yaml"
    path.write_text("apps:\n  - name: keyword-radar\n    uses_llm: true\n", encoding="utf-8")
    return path


def make(apps_file, *, auth_disabled=True, fail=False, **overrides):
    settings = Settings(
        posthog_api_key="phx_very_secret",
        posthog_project_id="42",
        auth_disabled=auth_disabled,
        app_env="development",
        apps_file=apps_file,
        session_secret="s" * 40,
        **overrides,
    )
    fake = FakeClient(fail=fail)
    return TestClient(create_app(settings, client=fake)), fake


def test_health_needs_no_sign_in(apps_file):
    client, _ = make(apps_file, auth_disabled=False)
    assert client.get("/api/health").json() == {"ok": True}


def test_status_lists_missing_names_without_secret_values(apps_file):
    client, _ = make(apps_file, auth_disabled=False)

    body = client.get("/api/status").json()

    assert body["configured"] is False
    assert "GOOGLE_CLIENT_ID" in body["missing"]
    assert "phx_very_secret" not in str(body)


def test_data_endpoints_require_sign_in(apps_file):
    client, _ = make(apps_file, auth_disabled=False)

    assert client.get("/api/overview").status_code == 401
    assert client.get("/api/apps/keyword-radar").status_code == 401
    assert client.get("/api/meta").status_code == 401


def test_overview_returns_all_panels_for_the_range(apps_file):
    client, fake = make(apps_file)

    body = client.get("/api/overview", params={"range": 45}).json()

    assert body["range"] == 45
    assert set(body["panels"]) == {"tiles", "daily", "heatmap", "apps"}
    assert body["llm_history_days"] == 30
    assert body["panels"]["apps"]["data"][0]["app"] == "keyword-radar"
    assert "generated_at" in body


@pytest.mark.parametrize("value", ["14", "abc", "0"])
def test_range_outside_whitelist_is_rejected(apps_file, value):
    client, fake = make(apps_file)

    assert client.get("/api/overview", params={"range": value}).status_code == 422
    assert fake.calls == []


@pytest.mark.parametrize("name", ["Keyword", "a'b", "a--b"])
def test_invalid_app_name_is_404_and_never_queried(apps_file, name):
    client, fake = make(apps_file)

    assert client.get(f"/api/apps/{name}").status_code == 404
    assert fake.calls == []


def test_app_page_reports_whether_the_app_is_registered(apps_file):
    client, _ = make(apps_file)

    assert client.get("/api/apps/keyword-radar").json()["registered"] is True
    assert client.get("/api/apps/unknown-app").json()["registered"] is False


def test_results_are_cached_and_refresh_is_throttled(apps_file):
    client, fake = make(apps_file)

    client.get("/api/overview")
    first = len(fake.calls)
    client.get("/api/overview")
    assert len(fake.calls) == first  # cached

    assert client.get("/api/overview", params={"refresh": "true"}).json()["refresh_throttled"] is False
    assert len(fake.calls) == 2 * first
    assert client.get("/api/overview", params={"refresh": "true"}).json()["refresh_throttled"] is True
    assert len(fake.calls) == 2 * first


def test_posthog_failure_shows_as_panel_errors_not_zeros(apps_file):
    client, _ = make(apps_file, fail=True)

    panels = client.get("/api/overview").json()["panels"]

    assert panels["tiles"] == {"status": "error", "error": "posthog_unavailable"}


def test_meta_gives_apps_and_posthog_link(apps_file):
    client, _ = make(apps_file)

    body = client.get("/api/meta").json()

    assert body["apps"] == [{"name": "keyword-radar", "uses_llm": True, "status": "planned"}]
    assert body["posthog_url"] == "https://eu.posthog.com/project/42"
    assert body["ranges"] == [7, 30, 45, 90]


def test_frontend_is_served_with_spa_fallback(apps_file, tmp_path):
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<html>admin</html>", encoding="utf-8")
    (static / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    settings = Settings(auth_disabled=True, app_env="development", apps_file=apps_file)
    client = TestClient(create_app(settings, client=FakeClient(), static_dir=static))

    assert client.get("/").text == "<html>admin</html>"
    assert client.get("/apps/keyword-radar").text == "<html>admin</html>"
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/api/nope").status_code == 404


def test_environment_defaults_to_production_and_is_echoed(apps_file):
    client, _ = make(apps_file)

    assert client.get("/api/overview").json()["environment"] == "production"
    assert client.get("/api/apps/keyword-radar", params={"env": "development"}).json()["environment"] == "development"


def test_unknown_environment_is_rejected(apps_file):
    client, fake = make(apps_file)

    assert client.get("/api/overview", params={"env": "staging"}).status_code == 422
    assert fake.calls == []


def test_meta_lists_environments(apps_file):
    client, _ = make(apps_file)

    assert client.get("/api/meta").json()["environments"] == ["production", "development"]
