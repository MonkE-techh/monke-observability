"""Who and what the current code is running for: a request, or a background job.

The request middleware opens a context per request; workers open one per job with `job_context()`.
LLM events read it, so a generation is attributed to the right user, route or job without passing ids around.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CallContext:
    app_name: str | None = None
    user_id: str | None = None  # already namespaced (app:id)
    browser_distinct_id: str | None = None
    session_id: str | None = None
    job: str | None = None
    trace_id: str | None = None
    scope: MutableMapping[str, Any] | None = field(default=None, repr=False)

    @property
    def route(self) -> str | None:
        """Route template of the current request, once the router has matched it."""
        if self.scope is None:
            return None
        return route_template(self.scope)

    @property
    def distinct_id(self) -> str | None:
        return self.user_id or self.browser_distinct_id


_PARAM = re.compile(r"\{([^}:]+)(?::[^}]*)?\}")


def route_template(scope: MutableMapping[str, Any]) -> str | None:
    """Full route template, e.g. `/api/auth/me`.

    Newer FastAPI (0.162+) reports routes from `include_router(prefix=...)` without that prefix, so the prefix is
    recovered from the request path: fill the route's own template with the matched path params and keep whatever
    comes before it. If the prefix would contain a param value (an id), the route's own template is used instead.
    """
    route = scope.get("route")
    template = getattr(route, "path", None)
    if not isinstance(template, str):
        return None
    path = scope.get("path")
    params = scope.get("path_params") or {}
    if not isinstance(path, str):
        return template
    try:
        rendered = _PARAM.sub(lambda m: str(params[m.group(1)]), template)
    except KeyError:
        return template
    if rendered == path or not path.endswith(rendered):
        return template
    prefix = path[: len(path) - len(rendered)]
    segments = set(prefix.split("/"))
    if any(str(v) in segments for v in params.values()):
        return template
    return prefix + template


_current: ContextVar[CallContext | None] = ContextVar("monke_observability_context", default=None)


def current() -> CallContext | None:
    return _current.get()


@contextmanager
def use_context(ctx: CallContext) -> Iterator[CallContext]:
    token = _current.set(ctx)
    try:
        yield ctx
    finally:
        _current.reset(token)


@contextmanager
def job_context(
    job: str, *, user_id: object = None, trace_id: str | None = None, app_name: str | None = None
) -> Iterator[CallContext]:
    """Attribute everything inside (LLM generations) to a background job and, optionally, the user who started it.

    `user_id` is namespaced with the app name (from `app_name` or init()).
    """
    from monke_observability import core

    obs = core.get()
    name = app_name or (obs.app_name if obs else None)
    uid = core.namespaced_user_id(name, user_id) if name else None
    with use_context(CallContext(app_name=name, user_id=uid, job=job, trace_id=trace_id)) as ctx:
        try:
            yield ctx
        except Exception as exc:
            # Job runners (arq, cron) catch job errors themselves, so the SDK's global hook never sees them.
            # Read the user now: the job may have learnt it after starting (e.g. once its record loaded).
            if obs is not None:
                props: dict[str, Any] = {"job": job}
                if ctx.user_id:
                    props["user_id"] = ctx.user_id
                if trace_id:
                    props["$ai_trace_id"] = trace_id
                obs.capture_exception(exc, distinct_id=ctx.user_id, properties=props)
            raise
