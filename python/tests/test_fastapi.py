from __future__ import annotations

import logging

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from monke_observability import Observability
from monke_observability.fastapi import TRACING_HEADERS, RequestEventsMiddleware, set_user


def make_app(obs: Observability, **middleware_kwargs) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestEventsMiddleware, obs=obs, **middleware_kwargs)

    async def current_user(request: Request) -> int:
        set_user(request, 42)
        return 42

    @app.get("/api/creators/{creator_id}")
    async def get_creator(creator_id: int):
        return {"id": creator_id}

    @app.get("/api/me")
    async def me(user: int = Depends(current_user)):
        return {"user": user}

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    @app.get("/api/missing")
    async def missing():
        raise HTTPException(404, "nope")

    @app.get("/api/boom")
    async def boom():
        raise RuntimeError("secret detail that must not be sent")

    return app


@pytest.fixture
def obs(fake) -> Observability:
    return Observability(app_name="radar", environment="production", client=fake)


def only_event(fake) -> dict:
    assert len(fake.events) == 1, fake.events
    return fake.events[0]


def test_records_route_template_not_the_raw_url(obs, fake):
    TestClient(make_app(obs)).get("/api/creators/7?token=abc")

    sent = only_event(fake)
    props = sent["properties"]
    assert sent["event"] == "api_request"
    assert props["route"] == "/api/creators/{creator_id}"
    assert props["method"] == "GET"
    assert props["status_code"] == 200
    assert props["status_class"] == "2xx"
    assert isinstance(props["duration_ms"], float) and props["duration_ms"] >= 0
    assert props["app_name"] == "radar"
    assert "abc" not in repr(sent)


def test_signed_in_user_becomes_namespaced_distinct_id(obs, fake):
    TestClient(make_app(obs)).get("/api/me")

    sent = only_event(fake)
    assert sent["distinct_id"] == "radar:42"
    assert sent["properties"]["user_id"] == "radar:42"


def test_browser_headers_link_anonymous_request_to_session(obs, fake):
    TestClient(make_app(obs)).get(
        "/api/creators/1", headers={"X-POSTHOG-DISTINCT-ID": "0193abc-anon", "X-POSTHOG-SESSION-ID": "0193-sess"}
    )

    sent = only_event(fake)
    assert sent["distinct_id"] == "0193abc-anon"
    assert sent["properties"]["$session_id"] == "0193-sess"
    assert "user_id" not in sent["properties"]


def test_server_user_wins_over_browser_distinct_id_header(obs, fake):
    TestClient(make_app(obs)).get("/api/me", headers={"X-POSTHOG-DISTINCT-ID": "radar:999"})

    assert only_event(fake)["distinct_id"] == "radar:42"


@pytest.mark.parametrize("bad", ["x" * 300, "has spaces", "<script>"])
def test_malformed_tracing_headers_are_ignored(obs, fake, bad):
    headers = {"X-POSTHOG-DISTINCT-ID": bad, "X-POSTHOG-SESSION-ID": bad}
    TestClient(make_app(obs)).get("/api/creators/1", headers=headers)

    sent = only_event(fake)
    assert sent["distinct_id"] is None
    assert "$session_id" not in sent["properties"]


def test_request_without_identity_is_personless(obs, fake):
    TestClient(make_app(obs)).get("/api/creators/1")

    assert only_event(fake)["properties"]["$process_person_profile"] is False


def test_health_checks_and_preflight_requests_are_not_recorded(obs, fake):
    client = TestClient(make_app(obs))
    client.get("/api/health")
    client.options("/api/creators/1")

    assert fake.events == []


def test_extra_excluded_routes_are_not_recorded(obs, fake):
    TestClient(make_app(obs, exclude_routes={"/api/creators/{creator_id}"})).get("/api/creators/1")

    assert fake.events == []


def test_unknown_path_is_recorded_as_unmatched(obs, fake):
    TestClient(make_app(obs)).get("/wp-admin/secret-123")

    props = only_event(fake)["properties"]
    assert props["route"] == "unmatched"
    assert props["status_code"] == 404


def test_handled_http_error_keeps_its_status(obs, fake):
    TestClient(make_app(obs)).get("/api/missing")

    props = only_event(fake)["properties"]
    assert (props["status_code"], props["status_class"]) == (404, "4xx")


def test_unhandled_exception_is_recorded_as_500_without_its_message(obs, fake):
    TestClient(make_app(obs), raise_server_exceptions=False).get("/api/boom")

    sent = only_event(fake)
    assert sent["properties"]["status_code"] == 500
    assert sent["properties"]["error_type"] == "RuntimeError"
    assert "secret detail" not in repr(sent)


def test_sampling_drops_successes_but_keeps_errors(fake):
    obs = Observability(app_name="radar", environment="production", client=fake, sample_rate=0.1)
    client = TestClient(make_app(obs, random=lambda: 0.5), raise_server_exceptions=False)

    client.get("/api/creators/1")
    client.get("/api/boom")

    assert [e["properties"]["status_code"] for e in fake.events] == [500]
    assert fake.events[0]["properties"]["sample_rate"] == 0.1


def test_sampled_in_request_records_its_sample_rate(fake):
    obs = Observability(app_name="radar", environment="production", client=fake, sample_rate=0.1)
    TestClient(make_app(obs, random=lambda: 0.05)).get("/api/creators/1")

    assert only_event(fake)["properties"]["sample_rate"] == 0.1


def test_each_request_is_also_logged_with_structured_attributes(obs, fake, caplog):
    with caplog.at_level(logging.INFO, logger="monke_observability.request"):
        TestClient(make_app(obs)).get("/api/creators/3")

    record = next(r for r in caplog.records if r.name == "monke_observability.request")
    assert record.event_type == "api_request"
    assert record.route == "/api/creators/{creator_id}"
    assert record.status_code == 200
    assert record.app_name == "radar"


def test_tracing_headers_constant_lists_both_posthog_headers():
    assert set(TRACING_HEADERS) == {"X-POSTHOG-DISTINCT-ID", "X-POSTHOG-SESSION-ID"}


def test_route_template_keeps_the_include_router_prefix(obs, fake):
    from fastapi import APIRouter

    inner = APIRouter(prefix="/auth")

    @inner.get("/sessions/{session_id}/items/{item_id:int}")
    async def item(session_id: str, item_id: int):
        return {}

    app = FastAPI()
    app.add_middleware(RequestEventsMiddleware, obs=obs)
    app.include_router(inner, prefix="/api/v1")

    TestClient(app).get("/api/v1/auth/sessions/abc/items/42")

    assert only_event(fake)["properties"]["route"] == "/api/v1/auth/sessions/{session_id}/items/{item_id:int}"


def test_prefix_containing_an_id_is_never_sent(obs, fake):
    from fastapi import APIRouter

    inner = APIRouter()

    @inner.get("/items")
    async def items(tenant_id: str):
        return {}

    app = FastAPI()
    app.add_middleware(RequestEventsMiddleware, obs=obs)
    app.include_router(inner, prefix="/tenants/{tenant_id}")

    TestClient(app).get("/tenants/acme-42/items")

    route = only_event(fake)["properties"]["route"]
    assert "acme-42" not in route
