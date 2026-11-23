"""ASGI middleware that records every API request as an `api_request` event and a structured log line.

Works with FastAPI and any Starlette app; it does not import FastAPI.

    from monke_observability import init
    from monke_observability.fastapi import TRACING_HEADERS, RequestEventsMiddleware, set_user

    init()                                   # reads APP_NAME, POSTHOG_PROJECT_TOKEN, ...
    app.add_middleware(RequestEventsMiddleware, exclude_routes={"/api/jobs/{job_id}/status"})
    # CORS must allow the browser's tracing headers:
    app.add_middleware(CORSMiddleware, allow_headers=["Content-Type", *TRACING_HEADERS], ...)

    async def require_user(request: Request) -> User:
        user = ...                           # the app's own authentication
        set_user(request, user.id)           # the server-side id always wins over browser headers
        return user
"""

from __future__ import annotations

import logging
import random as _random
import re
import time
from collections.abc import Callable, Collection
from typing import Any

from monke_observability import core
from monke_observability.context import CallContext, route_template, use_context

TRACING_HEADERS = ("X-POSTHOG-DISTINCT-ID", "X-POSTHOG-SESSION-ID")
DEFAULT_EXCLUDED_ROUTES = frozenset({"/health", "/healthz", "/api/health", "/api/healthz", "/"})
SKIPPED_METHODS = frozenset({"OPTIONS", "HEAD"})

# Browser ids are UUID-like; anything else is ignored rather than sent. They link events to
# sessions only and are never trusted for authorization.
_HEADER_ID = re.compile(r"^[A-Za-z0-9_\-:.]{1,200}$")
_STATE_KEY = "monke_observability"

request_log = logging.getLogger("monke_observability.request")


def set_user(request: Any, user_id: object) -> None:
    """Record the authenticated user for the current request (call it from the auth dependency)."""
    scope = request.scope
    ctx: CallContext | None = scope.get("state", {}).get(_STATE_KEY)
    if ctx is None:
        return  # middleware not installed (e.g. in an app's own tests)
    ctx.user_id = core.namespaced_user_id(ctx.app_name or "", user_id)


def _header(scope: dict[str, Any], name: str) -> str | None:
    wanted = name.lower().encode("latin-1")
    for key, value in scope.get("headers", ()):
        if key.lower() == wanted:
            text = value.decode("latin-1").strip()
            return text if _HEADER_ID.match(text) else None
    return None


class RequestEventsMiddleware:
    def __init__(
        self,
        app: Any,
        *,
        obs: core.Observability | None = None,
        exclude_routes: Collection[str] = (),
        random: Callable[[], float] = _random.random,
    ) -> None:
        self.app = app
        self._obs = obs
        self._excluded = DEFAULT_EXCLUDED_ROUTES | frozenset(exclude_routes)
        self._random = random

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        obs = self._obs or core.get()
        if scope["type"] != "http" or obs is None or scope.get("method") in SKIPPED_METHODS:
            await self.app(scope, receive, send)
            return

        ctx = CallContext(
            app_name=obs.app_name,
            browser_distinct_id=_header(scope, "X-POSTHOG-DISTINCT-ID"),
            session_id=_header(scope, "X-POSTHOG-SESSION-ID"),
            scope=scope,
        )
        scope.setdefault("state", {})[_STATE_KEY] = ctx

        status_code = 500
        error_type: str | None = None

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        started = time.perf_counter()
        try:
            with use_context(ctx):
                await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            status_code, error_type = 500, type(exc).__name__
            self._report(obs, scope, ctx, exc)
            raise
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            self._record(obs, scope, ctx, status_code, duration_ms, error_type)

    @staticmethod
    def _report(obs: core.Observability, scope: dict[str, Any], ctx: CallContext, exc: Exception) -> None:
        props: dict[str, Any] = {"route": route_template(scope) or "unmatched", "method": scope.get("method")}
        if ctx.user_id:
            props["user_id"] = ctx.user_id
        if ctx.session_id:
            props["$session_id"] = ctx.session_id
        obs.capture_exception(exc, distinct_id=ctx.distinct_id, properties=props)

    def _record(
        self,
        obs: core.Observability,
        scope: dict[str, Any],
        ctx: CallContext,
        status_code: int,
        duration_ms: float,
        error_type: str | None,
    ) -> None:
        route = route_template(scope) or "unmatched"
        if route in self._excluded:
            return
        if status_code < 500 and obs.sample_rate < 1 and self._random() >= obs.sample_rate:
            return

        props: dict[str, Any] = {
            "method": scope.get("method"),
            "route": route,
            "status_code": status_code,
            "status_class": f"{status_code // 100}xx",
            "duration_ms": duration_ms,
            "sample_rate": obs.sample_rate,
        }
        if ctx.user_id:
            props["user_id"] = ctx.user_id
        if ctx.session_id:
            props["$session_id"] = ctx.session_id
        if error_type:
            props["error_type"] = error_type

        try:
            obs.capture("api_request", distinct_id=ctx.distinct_id, properties=props)
        except Exception:
            # Telemetry must never break a request; the failure is still visible in the app's logs.
            request_log.exception("monke-observability: failed to queue api_request event")

        level = logging.ERROR if status_code >= 500 else logging.WARNING if status_code >= 400 else logging.INFO
        request_log.log(
            level,
            "%s %s %s %.0fms",
            props["method"],
            route,
            status_code,
            duration_ms,
            extra={
                "event_type": "api_request",
                "app_name": obs.app_name,
                "environment": obs.environment,
                **{k: v for k, v in props.items() if not k.startswith("$")},
                "posthogDistinctId": ctx.distinct_id,
                "sessionId": ctx.session_id,
            },
        )
