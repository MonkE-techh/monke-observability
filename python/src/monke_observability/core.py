"""The shared PostHog client wrapper: app tagging, identity rules and settings from the environment."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Any, Protocol

log = logging.getLogger("monke_observability")

DEFAULT_HOST = "https://eu.i.posthog.com"
_APP_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class PosthogLike(Protocol):
    def capture(self, event: str, **kwargs: Any) -> Any: ...
    def capture_ai(self, event: str, **kwargs: Any) -> Any: ...
    def capture_exception(self, exception: BaseException, **kwargs: Any) -> Any: ...
    def flush(self, timeout_seconds: float | None = 10) -> None: ...


def pseudonymous_id(value: object) -> str | None:
    """Stable opaque id for apps that know users only by email: first 16 hex chars of sha256(trimmed, lower-case).

    Unsalted, so it is pseudonymous rather than anonymous: anyone who knows an email can recompute it.
    The browser package's `pseudonymousId` gives the same value.
    """
    if value is None:
        return None
    normalised = str(value).strip().lower()
    if not normalised:
        return None
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:16]


def namespaced_user_id(app_name: str, user_id: object) -> str | None:
    """`app:id`, so users of different apps never merge into one PostHog person. Empty/None gives None."""
    if user_id is None:
        return None
    raw = str(user_id).strip()
    if not raw:
        return None
    prefix = f"{app_name}:"
    return raw if raw.startswith(prefix) else prefix + raw


class Observability:
    """Sends events for one app. With no client (no token), every call is a no-op."""

    def __init__(
        self,
        *,
        app_name: str,
        environment: str,
        client: PosthogLike | None,
        sample_rate: float = 1.0,
    ) -> None:
        self.app_name = app_name
        self.environment = environment
        self.sample_rate = sample_rate
        self._client = client

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def _props(self, distinct_id: str | None, properties: dict[str, Any]) -> dict[str, Any]:
        props = {**properties, "app_name": self.app_name, "environment": self.environment}
        if distinct_id is None:
            props["$process_person_profile"] = False
        return props

    def capture(self, event: str, *, distinct_id: str | None, properties: dict[str, Any]) -> None:
        if self._client is None:
            return
        self._client.capture(event, distinct_id=distinct_id, properties=self._props(distinct_id, properties))

    def capture_ai(self, event: str, *, distinct_id: str | None, properties: dict[str, Any]) -> None:
        if self._client is None:
            return
        self._client.capture_ai(event, distinct_id=distinct_id, properties=self._props(distinct_id, properties))

    def capture_exception(
        self, exception: BaseException, *, distinct_id: str | None, properties: dict[str, Any]
    ) -> None:
        """Send to PostHog Error Tracking (message and stack trace; local variable values are never sent)."""
        if self._client is None:
            return
        try:
            self._client.capture_exception(
                exception, distinct_id=distinct_id, properties=self._props(distinct_id, properties)
            )
        except Exception:
            # Reporting an error must never raise a second one.
            log.exception("monke-observability: failed to queue exception event")

    def flush(self, timeout_seconds: float | None = 10) -> None:
        if self._client is not None:
            self._client.flush(timeout_seconds=timeout_seconds)


_current: Observability | None = None


def _sample_rate(value: str | float | None) -> float:
    if value is None or value == "":
        return 1.0
    try:
        rate = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"invalid sample rate {value!r}: expected a number in (0, 1]") from None
    if not 0 < rate <= 1:
        raise ValueError(f"invalid sample rate {value!r}: expected a number in (0, 1]")
    return rate


def init(
    *,
    app_name: str | None = None,
    environment: str | None = None,
    token: str | None = None,
    host: str | None = None,
    sample_rate: float | None = None,
    client: PosthogLike | None = None,
) -> Observability:
    """Configure instrumentation for this process. Arguments override APP_NAME, APP_ENV,
    POSTHOG_PROJECT_TOKEN, POSTHOG_HOST and MONKE_SAMPLE_RATE. Without a token nothing is sent."""
    global _current
    name = app_name or os.environ.get("APP_NAME", "")
    if not name:
        raise ValueError("APP_NAME is not set: every event must carry the app's name")
    if not _APP_NAME.match(name):
        raise ValueError(f"app name {name!r} must be kebab-case, e.g. 'creator-curation'")
    env = environment or os.environ.get("APP_ENV") or "production"
    rate = _sample_rate(sample_rate if sample_rate is not None else os.environ.get("MONKE_SAMPLE_RATE"))

    if client is None:
        project_token = token or os.environ.get("POSTHOG_PROJECT_TOKEN")
        if project_token:
            from posthog import Posthog

            client = Posthog(
                project_token,
                host=host or os.environ.get("POSTHOG_HOST") or DEFAULT_HOST,
                # Uncaught process-level errors (start-up, threads); request and job errors are sent explicitly.
                enable_exception_autocapture=True,
                capture_exception_code_variables=False,
            )
        else:
            log.warning("POSTHOG_PROJECT_TOKEN is not set: monke-observability sends nothing for %s", name)

    _current = Observability(app_name=name, environment=env, client=client, sample_rate=rate)
    return _current


def get() -> Observability | None:
    """The instance set up by init(), or None before init()."""
    return _current
