"""Turns query results into panels. Each panel is ok / empty / error on its own, so one failure never shows as zero."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from monke_admin import queries
from monke_admin.posthog import QueryError
from monke_admin.registry import AppEntry

Run = Callable[[str, str], Awaitable[list[dict[str, Any]]]]
Panel = dict[str, Any]


def ok(data: Any) -> Panel:
    return {"status": "ok", "data": data}


EMPTY: Panel = {"status": "empty"}


def _num(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _count(value: Any) -> int:
    return round(_num(value))


async def _rows(run: Run, sql: str, name: str) -> list[dict[str, Any]] | Panel:
    try:
        return await run(sql, name)
    except QueryError as exc:
        return {"status": "error", "error": exc.code}


async def _list_panel(run: Run, sql: str, name: str) -> Panel:
    rows = await _rows(run, sql, name)
    if isinstance(rows, dict):
        return rows
    return ok(rows) if rows else EMPTY


async def _tiles(run: Run, days: int, app: str | None, env: str) -> Panel:
    rows = await _rows(run, queries.tiles(days, app, env), "tiles")
    if isinstance(rows, dict):
        return rows
    row = rows[0] if rows else {}
    requests, visitors, llm_calls = (
        _count(row.get("requests")),
        _count(row.get("visitors")),
        _count(row.get("llm_calls")),
    )
    if not (requests or visitors or llm_calls):
        return EMPTY
    errors = _count(row.get("errors_5xx"))
    return ok(
        {
            "requests": requests,
            "errors_5xx": errors,
            "error_rate": errors / requests if requests else None,
            "avg_ms": row.get("avg_ms"),
            "slowest_ms": row.get("slowest_ms"),
            "visitors": visitors,
            "llm_calls": llm_calls,
            "llm_cost_usd": _num(row.get("llm_cost_usd")),
        }
    )


async def _apps(run: Run, registry: list[AppEntry], days: int, env: str) -> Panel:
    rows = await _rows(run, queries.apps(days, env), "apps")
    if isinstance(rows, dict):
        return rows
    known = {a.name: a for a in registry}
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = row.get("app")
        if not name:
            continue
        entry = known.get(name)
        seen[name] = {
            "app": name,
            "registered": entry is not None,
            "requests": _count(row.get("requests")),
            "errors_5xx": _count(row.get("errors_5xx")),
            "avg_ms": row.get("avg_ms"),
            "slowest_ms": row.get("slowest_ms"),
            "visitors": _count(row.get("visitors")),
            "llm_cost_usd": _num(row.get("llm_cost_usd")),
            "last_event": row.get("last_event"),
            "uses_llm": entry.uses_llm if entry else False,
        }
    for entry in registry:
        seen.setdefault(
            entry.name,
            {
                "app": entry.name,
                "registered": True,
                "requests": 0,
                "errors_5xx": 0,
                "avg_ms": None,
                "slowest_ms": None,
                "visitors": 0,
                "llm_cost_usd": 0,
                "last_event": None,
                "uses_llm": entry.uses_llm,
            },
        )
    return ok(sorted(seen.values(), key=lambda r: (not r["registered"], -r["requests"], r["app"])))


async def _visitors(run: Run, days: int, app: str, env: str) -> Panel:
    kinds = list(queries.VISITOR_PROPERTIES)
    parts = await asyncio.gather(*(_rows(run, queries.visitors(days, app, k, env), f"visitors_{k}") for k in kinds))
    for part in parts:
        if isinstance(part, dict):
            return part
    if not any(parts):
        return EMPTY
    return ok(dict(zip(kinds, parts, strict=True)))


async def overview(run: Run, registry: list[AppEntry], days: int, env: str = "production") -> dict[str, Panel]:
    tiles, daily, heatmap, apps = await asyncio.gather(
        _tiles(run, days, None, env),
        _list_panel(run, queries.daily(days, env=env), "daily"),
        _list_panel(run, queries.heatmap(days, env=env), "heatmap"),
        _apps(run, registry, days, env),
    )
    return {"tiles": tiles, "daily": daily, "heatmap": heatmap, "apps": apps}


async def app_detail(run: Run, app: str, days: int, env: str = "production") -> dict[str, Panel]:
    names = ("tiles", "daily", "heatmap", "routes", "errors", "llm_models", "llm_sources", "llm_users", "visitors")
    results = await asyncio.gather(
        _tiles(run, days, app, env),
        _list_panel(run, queries.daily(days, app, env), "daily"),
        _list_panel(run, queries.heatmap(days, app, env), "heatmap"),
        _list_panel(run, queries.routes(days, app, env), "routes"),
        _list_panel(run, queries.errors(days, app, env), "errors"),
        _list_panel(run, queries.llm_models(days, app, env), "llm_models"),
        _list_panel(run, queries.llm_sources(days, app, env), "llm_sources"),
        _list_panel(run, queries.llm_users(days, app, env), "llm_users"),
        _visitors(run, days, app, env),
    )
    return dict(zip(names, results, strict=True))
