"""Runs HogQL queries against PostHog's query API with the personal API key (query:read scope)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from monke_admin.settings import Settings

log = logging.getLogger(__name__)

MAX_CONCURRENT = 3  # PostHog allows 3 concurrent queries per project
TIMEOUT_S = 15.0


class QueryError(Exception):
    """`code` is safe to show in the UI: not_configured, posthog_timeout, posthog_rate_limited, posthog_unavailable."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class QueryClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._settings = settings
        self._transport = transport
        self._limit = asyncio.Semaphore(MAX_CONCURRENT)

    async def run(self, sql: str, *, name: str) -> list[dict[str, Any]]:
        s = self._settings
        if not s.posthog_configured:
            raise QueryError("not_configured")
        url = f"{s.posthog_app_host}/api/projects/{s.posthog_project_id}/query"
        body = {"query": {"kind": "HogQLQuery", "query": sql}, "name": f"monke-admin: {name}"}
        async with self._limit:
            try:
                async with httpx.AsyncClient(transport=self._transport, timeout=TIMEOUT_S) as http:
                    response = await http.post(url, json=body, headers={"Authorization": f"Bearer {s.posthog_api_key}"})
            except httpx.TimeoutException:
                log.warning("posthog query %s timed out", name)
                raise QueryError("posthog_timeout") from None
            except httpx.HTTPError as exc:
                log.warning("posthog query %s failed: %s", name, type(exc).__name__)
                raise QueryError("posthog_unavailable") from None

        if response.status_code == 429:
            log.warning("posthog query %s rate limited", name)
            raise QueryError("posthog_rate_limited")
        if response.status_code >= 400:
            # The body can echo the query; log only the status.
            log.warning("posthog query %s returned HTTP %s", name, response.status_code)
            raise QueryError("posthog_unavailable")
        try:
            data = response.json()
            columns, results = data["columns"], data["results"]
        except (ValueError, KeyError, TypeError):
            log.warning("posthog query %s returned an unexpected body", name)
            raise QueryError("posthog_unavailable") from None
        return [dict(zip(columns, row, strict=False)) for row in results]
