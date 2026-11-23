from __future__ import annotations

import pytest

from monke_admin import queries
from monke_admin.panels import app_detail, overview
from monke_admin.posthog import QueryError
from monke_admin.registry import AppEntry

REGISTRY = [AppEntry("engagement-bot-checker", uses_llm=True, status="pilot"), AppEntry("keyword-radar", True)]


class FakeRun:
    """Answers queries by their name; records the SQL it was given."""

    def __init__(self, answers: dict):
        self.answers = answers
        self.sql: dict[str, str] = {}

    async def __call__(self, sql: str, name: str):
        self.sql[name] = sql
        answer = self.answers.get(name, [])
        if isinstance(answer, Exception):
            raise answer
        return answer


TILES_ROW = {
    "requests": 1000.0,
    "errors_5xx": 5,
    "avg_ms": 120.5,
    "slowest_ms": 9000.0,
    "visitors": 40,
    "llm_calls": 12,
    "llm_cost_usd": 0.42,
}


# --- SQL --------------------------------------------------------------------------------------------


def test_request_counts_are_scaled_by_sample_rate_but_5xx_are_not():
    assert (
        queries.WEIGHT
        == "if(toInt(properties.status_code) >= 500, 1, 1 / coalesce(toFloat(properties.sample_rate), 1))"
    )
    sql = queries.tiles(30)
    assert f"sumIf({queries.WEIGHT}, event = 'api_request') AS requests" in sql
    assert "countIf(event = 'api_request' AND toInt(properties.status_code) >= 500) AS errors_5xx" in sql


def test_llm_cost_falls_back_to_input_plus_output_cost():
    assert "$ai_total_cost_usd" in queries.COST and "$ai_input_cost_usd" in queries.COST
    assert queries.COST in queries.tiles(30)


def test_times_are_bucketed_in_ist():
    assert "toTimeZone(timestamp, 'Asia/Kolkata')" in queries.daily(7)
    assert "toHour(toTimeZone(timestamp, 'Asia/Kolkata'))" in queries.heatmap(7)


def test_range_and_app_filter_are_in_the_where_clause():
    sql = queries.routes(45, "keyword-radar")
    assert "timestamp >= now() - INTERVAL 45 DAY" in sql
    assert "properties.app_name = 'keyword-radar'" in sql


@pytest.mark.parametrize("days", [0, 1, 31, 365, -7])
def test_ranges_outside_the_whitelist_are_rejected(days):
    with pytest.raises(ValueError):
        queries.tiles(days)


@pytest.mark.parametrize("app", ["x' OR 1=1 --", "Radar", "", "a b"])
def test_unsafe_app_names_never_reach_sql(app):
    with pytest.raises(ValueError):
        queries.routes(30, app)


# --- overview ---------------------------------------------------------------------------------------


async def test_overview_tiles_include_error_rate():
    result = await overview(FakeRun({"tiles": [TILES_ROW]}), REGISTRY, 30)

    tiles = result["tiles"]
    assert tiles["status"] == "ok"
    assert tiles["data"]["requests"] == 1000
    assert tiles["data"]["error_rate"] == pytest.approx(0.005)


async def test_no_events_at_all_is_empty_not_zero():
    zero = dict.fromkeys(TILES_ROW, 0)
    result = await overview(FakeRun({"tiles": [zero]}), REGISTRY, 30)

    assert result["tiles"] == {"status": "empty"}
    assert result["daily"] == {"status": "empty"}


async def test_registered_app_without_events_is_listed_and_unregistered_app_is_flagged():
    rows = [
        {
            "app": "engagement-bot-checker",
            "requests": 10.0,
            "errors_5xx": 1,
            "avg_ms": 100.0,
            "slowest_ms": 500.0,
            "visitors": 3,
            "llm_cost_usd": 0.1,
            "last_event": "2026-11-23T10:00:00Z",
        },
        {
            "app": "mystery-app",
            "requests": 2.0,
            "errors_5xx": 0,
            "avg_ms": 50.0,
            "slowest_ms": 60.0,
            "visitors": 0,
            "llm_cost_usd": 0.0,
            "last_event": "2026-11-22T10:00:00Z",
        },
    ]
    result = await overview(FakeRun({"apps": rows}), REGISTRY, 7)

    by_name = {r["app"]: r for r in result["apps"]["data"]}
    assert by_name["engagement-bot-checker"]["registered"] is True
    assert by_name["keyword-radar"] == {
        "app": "keyword-radar",
        "registered": True,
        "requests": 0,
        "errors_5xx": 0,
        "avg_ms": None,
        "slowest_ms": None,
        "visitors": 0,
        "llm_cost_usd": 0,
        "last_event": None,
        "uses_llm": True,
    }
    assert by_name["mystery-app"]["registered"] is False


async def test_one_failing_query_only_breaks_its_own_panel():
    run = FakeRun({"tiles": [TILES_ROW], "daily": QueryError("posthog_timeout")})

    result = await overview(run, REGISTRY, 30)

    assert result["daily"] == {"status": "error", "error": "posthog_timeout"}
    assert result["tiles"]["status"] == "ok"


# --- app detail -------------------------------------------------------------------------------------


async def test_app_detail_has_every_panel_and_filters_by_app():
    run = FakeRun({"tiles": [TILES_ROW]})

    result = await app_detail(run, "keyword-radar", 30)

    assert set(result) == {
        "tiles",
        "daily",
        "heatmap",
        "routes",
        "errors",
        "llm_models",
        "llm_sources",
        "llm_users",
        "visitors",
    }
    assert all("properties.app_name = 'keyword-radar'" in sql for sql in run.sql.values())


async def test_recent_errors_are_newest_first_rows():
    errors = [
        {
            "timestamp": "2026-11-23T10:00:00Z",
            "method": "GET",
            "route": "/a",
            "status_code": 500,
            "error_type": "RuntimeError",
            "user_id": None,
        }
    ]
    result = await app_detail(FakeRun({"errors": errors}), "keyword-radar", 7)

    assert result["errors"] == {"status": "ok", "data": errors}
    assert result["routes"] == {"status": "empty"}


async def test_visitor_breakdown_is_grouped_by_kind():
    run = FakeRun(
        {
            "visitors_country": [{"value": "India", "visitors": 30}],
            "visitors_device": [{"value": "Desktop", "visitors": 25}],
            "visitors_browser": [{"value": "Chrome", "visitors": 28}],
        }
    )
    result = await app_detail(run, "keyword-radar", 7)

    assert result["visitors"]["data"] == {
        "country": [{"value": "India", "visitors": 30}],
        "device": [{"value": "Desktop", "visitors": 25}],
        "browser": [{"value": "Chrome", "visitors": 28}],
    }
    assert "$geoip_country_name" in run.sql["visitors_country"]


async def test_visitor_breakdown_fails_as_a_whole_if_one_part_fails():
    run = FakeRun(
        {"visitors_country": [{"value": "India", "visitors": 1}], "visitors_device": QueryError("posthog_timeout")}
    )

    result = await app_detail(run, "keyword-radar", 7)

    assert result["visitors"] == {"status": "error", "error": "posthog_timeout"}


# --- environments ----------------------------------------------------------------------------------


def test_queries_default_to_production_and_can_switch_to_development():
    assert "properties.environment = 'production'" in queries.tiles(30)
    assert "properties.environment = 'development'" in queries.routes(30, "keyword-radar", env="development")


@pytest.mark.parametrize("env", ["prod", "staging' OR 1=1 --", ""])
def test_unknown_environments_never_reach_sql(env):
    with pytest.raises(ValueError):
        queries.daily(30, env=env)


async def test_every_panel_query_uses_the_chosen_environment():
    run = FakeRun({})

    await overview(run, REGISTRY, 30, env="development")
    await app_detail(run, "keyword-radar", 30, env="development")

    assert run.sql and all("properties.environment = 'development'" in sql for sql in run.sql.values())
