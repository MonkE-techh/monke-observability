from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from monke_admin.cache import TTLCache
from monke_admin.posthog import QueryClient, QueryError
from monke_admin.settings import Settings

SETTINGS = Settings(posthog_api_key="phx_test", posthog_project_id="42", posthog_app_host="https://eu.posthog.com")


def client_with(handler, settings=SETTINGS) -> QueryClient:
    return QueryClient(settings, transport=httpx.MockTransport(handler))


async def test_runs_hogql_query_and_returns_rows_keyed_by_column():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"columns": ["app", "n"], "results": [["radar", 3], ["cc", 1]]})

    rows = await client_with(handler).run("SELECT 1", name="apps")

    assert rows == [{"app": "radar", "n": 3}, {"app": "cc", "n": 1}]
    assert seen["url"] == "https://eu.posthog.com/api/projects/42/query"
    assert seen["auth"] == "Bearer phx_test"
    assert seen["body"] == {"query": {"kind": "HogQLQuery", "query": "SELECT 1"}, "name": "monke-admin: apps"}


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(429, json={}), "posthog_rate_limited"),
        (httpx.Response(500, text="boom"), "posthog_unavailable"),
        (httpx.Response(400, json={"detail": "bad query"}), "posthog_unavailable"),
        (httpx.Response(200, text="not json"), "posthog_unavailable"),
        (httpx.Response(200, json={"unexpected": True}), "posthog_unavailable"),
    ],
)
async def test_failures_become_query_errors(response, code):
    with pytest.raises(QueryError) as err:
        await client_with(lambda request: response).run("SELECT 1", name="x")

    assert err.value.code == code


async def test_timeout_becomes_query_error():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(QueryError) as err:
        await client_with(handler).run("SELECT 1", name="x")

    assert err.value.code == "posthog_timeout"


async def test_unconfigured_client_does_not_call_posthog():
    called = []

    with pytest.raises(QueryError) as err:
        await client_with(lambda r: called.append(r), settings=Settings()).run("SELECT 1", name="x")

    assert err.value.code == "not_configured"
    assert called == []


async def test_at_most_three_queries_run_at_once():
    running = 0
    peak = 0

    async def handler(request):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        return httpx.Response(200, json={"columns": [], "results": []})

    client = client_with(handler)
    await asyncio.gather(*(client.run("SELECT 1", name=str(i)) for i in range(8)))

    assert peak == 3


async def test_cache_reuses_result_within_ttl_and_force_recomputes():
    now = [0.0]
    cache = TTLCache(ttl_s=300, clock=lambda: now[0])
    calls = []

    async def compute():
        calls.append(1)
        return len(calls)

    assert await cache.get_or_compute("k", compute) == 1
    now[0] = 299
    assert await cache.get_or_compute("k", compute) == 1
    assert await cache.get_or_compute("k", compute, force=True) == 2
    now[0] = 1000
    assert await cache.get_or_compute("k", compute) == 3


async def test_cache_does_not_keep_failures():
    cache = TTLCache(ttl_s=300)
    attempts = []

    async def failing():
        attempts.append(1)
        raise QueryError("posthog_timeout")

    for _ in range(2):
        with pytest.raises(QueryError):
            await cache.get_or_compute("k", failing)

    assert len(attempts) == 2
