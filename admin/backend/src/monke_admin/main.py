"""FastAPI app: JSON API for the admin page, plus the built frontend from the same origin."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from monke_admin import auth, panels
from monke_admin.cache import TTLCache
from monke_admin.posthog import QueryClient
from monke_admin.queries import ENVIRONMENTS, RANGES
from monke_admin.registry import AppEntry, load_registry, valid_app_name
from monke_admin.settings import Settings

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
REFRESH_EVERY_S = 60
LLM_HISTORY_DAYS = 30  # PostHog keeps $ai_generation events 30 days on the free plan


class Client(Protocol):
    async def run(self, sql: str, *, name: str) -> list[dict[str, Any]]: ...


def _range(range: int = Query(30)) -> int:  # noqa: A002 - matches the query parameter name
    if range not in RANGES:
        raise HTTPException(422, f"range must be one of {list(RANGES)}")
    return range


def _environment(env: str = Query("production")) -> str:
    if env not in ENVIRONMENTS:
        raise HTTPException(422, f"env must be one of {list(ENVIRONMENTS)}")
    return env


def create_app(
    settings: Settings | None = None, client: Client | None = None, static_dir: Path | None = None
) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Monk-E admin", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    query_client = client or QueryClient(settings)
    cache = TTLCache(ttl_s=300)
    last_refresh: dict[str, float] = {}

    def registry() -> list[AppEntry]:
        return load_registry(settings.apps_file)

    def runner(force: bool):
        async def run(sql: str, name: str) -> list[dict[str, Any]]:
            return await cache.get_or_compute(sql, lambda: query_client.run(sql, name=name), force=force)

        return run

    def use_refresh(key: str, requested: bool) -> tuple[bool, bool]:
        """(force, throttled): a manual refresh bypasses the cache at most once a minute per page."""
        if not requested:
            return False, False
        now = time.monotonic()
        if now - last_refresh.get(key, -REFRESH_EVERY_S) < REFRESH_EVERY_S:
            return False, True
        last_refresh[key] = now
        return True, False

    def envelope(days: int, env: str, result: dict[str, Any], throttled: bool, **extra: Any) -> dict[str, Any]:
        return {
            "range": days,
            "environment": env,
            "generated_at": datetime.now(UTC).isoformat(),
            "llm_history_days": LLM_HISTORY_DAYS,
            "refresh_throttled": throttled,
            "panels": result,
            **extra,
        }

    app.include_router(auth.router())

    @app.get("/api/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/status")
    async def status_() -> dict[str, Any]:
        missing = settings.missing()
        return {"configured": not missing, "missing": missing}

    @app.get("/api/meta")
    async def meta(_: str = Depends(auth.require_admin)) -> dict[str, Any]:
        return {
            "apps": [{"name": a.name, "uses_llm": a.uses_llm, "status": a.status} for a in registry()],
            "ranges": list(RANGES),
            "environments": list(ENVIRONMENTS),
            "posthog_url": f"{settings.posthog_app_host}/project/{settings.posthog_project_id}",
        }

    @app.get("/api/overview")
    async def overview(
        days: int = Depends(_range),
        env: str = Depends(_environment),
        refresh: bool = False,
        _: str = Depends(auth.require_admin),
    ) -> dict[str, Any]:
        force, throttled = use_refresh(f"overview:{env}:{days}", refresh)
        result = await panels.overview(runner(force), registry(), days, env)
        return envelope(days, env, result, throttled)

    @app.get("/api/apps/{name}")
    async def app_page(
        name: str,
        days: int = Depends(_range),
        env: str = Depends(_environment),
        refresh: bool = False,
        _: str = Depends(auth.require_admin),
    ) -> dict[str, Any]:
        if not valid_app_name(name):
            raise HTTPException(404, "Unknown app")
        entry = next((a for a in registry() if a.name == name), None)
        force, throttled = use_refresh(f"app:{name}:{env}:{days}", refresh)
        result = await panels.app_detail(runner(force), name, days, env)
        return envelope(
            days,
            env,
            result,
            throttled,
            app=name,
            registered=entry is not None,
            uses_llm=bool(entry and entry.uses_llm),
        )

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    async def api_not_found(path: str) -> JSONResponse:
        return JSONResponse({"detail": "Not found"}, status_code=404)

    static = static_dir or STATIC_DIR
    index = static / "index.html"
    if (static / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str, request: Request):
        candidate = (static / path).resolve()
        if path and candidate.is_file() and static.resolve() in candidate.parents:
            return FileResponse(candidate)
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return JSONResponse({"detail": "Frontend not built: run `npm run build` in admin/frontend"}, status_code=503)

    return app
