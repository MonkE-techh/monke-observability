"""Fixed HogQL templates. The only values put into SQL are a whitelisted day count and a validated app name."""

from __future__ import annotations

from monke_admin.registry import valid_app_name

RANGES = (7, 30, 45, 90)
ENVIRONMENTS = ("production", "development")  # APP_ENV values the page can show; production is the default
TZ = "Asia/Kolkata"
LOCAL_TS = f"toTimeZone(timestamp, '{TZ}')"
STATUS = "toInt(properties.status_code)"
DURATION = "toFloat(properties.duration_ms)"
# Non-5xx requests may be sampled (sample_rate < 1); 5xx are always recorded, so they count once.
WEIGHT = f"if({STATUS} >= 500, 1, 1 / coalesce(toFloat(properties.sample_rate), 1))"
COST = (
    "coalesce(toFloat(properties.$ai_total_cost_usd), "
    "toFloat(properties.$ai_input_cost_usd) + toFloat(properties.$ai_output_cost_usd), 0)"
)


def _days(days: int) -> int:
    if days not in RANGES:
        raise ValueError(f"range must be one of {RANGES}")
    return days


def _env(env: str) -> str:
    if env not in ENVIRONMENTS:
        raise ValueError(f"environment must be one of {ENVIRONMENTS}")
    return env


def _where(days: int, app: str | None, env: str, events: tuple[str, ...]) -> str:
    names = ", ".join(f"'{e}'" for e in events)
    clauses = [
        f"event IN ({names})",
        f"timestamp >= now() - INTERVAL {_days(days)} DAY",
        f"properties.environment = '{_env(env)}'",
    ]
    if app is not None:
        if not valid_app_name(app):
            raise ValueError("invalid app name")
        clauses.append(f"properties.app_name = '{app}'")
    return " AND ".join(clauses)


def _request_stats(prefix: str = "event = 'api_request'") -> str:
    return (
        f"sumIf({WEIGHT}, {prefix}) AS requests, "
        f"countIf({prefix} AND {STATUS} >= 500) AS errors_5xx, "
        f"sumIf(({WEIGHT}) * {DURATION}, {prefix}) / nullIf(sumIf({WEIGHT}, {prefix}), 0) AS avg_ms, "
        f"maxIf({DURATION}, {prefix}) AS slowest_ms"
    )


_ALL = ("api_request", "$pageview", "$ai_generation")


def tiles(days: int, app: str | None = None, env: str = "production") -> str:
    return (
        f"SELECT {_request_stats()}, "
        "uniqIf(distinct_id, event = '$pageview') AS visitors, "
        "countIf(event = '$ai_generation') AS llm_calls, "
        f"sumIf({COST}, event = '$ai_generation') AS llm_cost_usd "
        f"FROM events WHERE {_where(days, app, env, _ALL)}"
    )


def apps(days: int, env: str = "production") -> str:
    return (
        f"SELECT properties.app_name AS app, {_request_stats()}, "
        "uniqIf(distinct_id, event = '$pageview') AS visitors, "
        f"sumIf({COST}, event = '$ai_generation') AS llm_cost_usd, "
        "max(timestamp) AS last_event "
        f"FROM events WHERE {_where(days, None, env, _ALL)} AND properties.app_name IS NOT NULL "
        "GROUP BY app ORDER BY requests DESC LIMIT 200"
    )


def daily(days: int, app: str | None = None, env: str = "production") -> str:
    return (
        f"SELECT toDate({LOCAL_TS}) AS day, properties.app_name AS app, sum({WEIGHT}) AS requests "
        f"FROM events WHERE {_where(days, app, env, ('api_request',))} "
        "GROUP BY day, app ORDER BY day LIMIT 10000"
    )


def heatmap(days: int, app: str | None = None, env: str = "production") -> str:
    return (
        f"SELECT toDayOfWeek({LOCAL_TS}) AS weekday, toHour({LOCAL_TS}) AS hour, sum({WEIGHT}) AS requests "
        f"FROM events WHERE {_where(days, app, env, ('api_request',))} "
        "GROUP BY weekday, hour ORDER BY weekday, hour"
    )


def routes(days: int, app: str, env: str = "production") -> str:
    return (
        f"SELECT properties.route AS route, {_request_stats('1 = 1')} "
        f"FROM events WHERE {_where(days, app, env, ('api_request',))} "
        "GROUP BY route ORDER BY requests DESC LIMIT 20"
    )


def errors(days: int, app: str, env: str = "production") -> str:
    return (
        "SELECT timestamp, properties.method AS method, properties.route AS route, "
        f"{STATUS} AS status_code, properties.error_type AS error_type, properties.user_id AS user_id "
        f"FROM events WHERE {_where(days, app, env, ('api_request',))} AND {STATUS} >= 500 "
        "ORDER BY timestamp DESC LIMIT 50"
    )


_LLM = ("$ai_generation",)


def llm_models(days: int, app: str, env: str = "production") -> str:
    return (
        "SELECT properties.$ai_model AS model, count() AS calls, "
        "sum(toInt(properties.$ai_input_tokens)) AS input_tokens, "
        "sum(toInt(properties.$ai_output_tokens)) AS output_tokens, "
        f"sum({COST}) AS cost_usd, "
        "countIf(toString(properties.$ai_is_error) IN ('true', '1')) AS errors "
        f"FROM events WHERE {_where(days, app, env, _LLM)} "
        "GROUP BY model ORDER BY cost_usd DESC LIMIT 50"
    )


def llm_sources(days: int, app: str, env: str = "production") -> str:
    return (
        "SELECT coalesce(properties.job, properties.route, 'other') AS source, count() AS calls, "
        f"sum({COST}) AS cost_usd "
        f"FROM events WHERE {_where(days, app, env, _LLM)} "
        "GROUP BY source ORDER BY cost_usd DESC LIMIT 20"
    )


def llm_users(days: int, app: str, env: str = "production") -> str:
    return (
        f"SELECT properties.user_id AS user_id, count() AS calls, sum({COST}) AS cost_usd "
        f"FROM events WHERE {_where(days, app, env, _LLM)} AND properties.user_id IS NOT NULL "
        "GROUP BY user_id ORDER BY cost_usd DESC LIMIT 10"
    )


VISITOR_PROPERTIES = {"country": "$geoip_country_name", "device": "$device_type", "browser": "$browser"}


def visitors(days: int, app: str, kind: str, env: str = "production") -> str:
    prop = VISITOR_PROPERTIES[kind]
    return (
        f"SELECT coalesce(properties.{prop}, 'Unknown') AS value, uniq(distinct_id) AS visitors "
        f"FROM events WHERE {_where(days, app, env, ('$pageview',))} "
        "GROUP BY value ORDER BY visitors DESC LIMIT 10"
    )
