from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from monke_observability import Observability, init
from monke_observability.context import job_context
from monke_observability.fastapi import RequestEventsMiddleware, set_user


def test_capture_exception_is_tagged_with_app(fake):
    obs = Observability(app_name="radar", environment="production", client=fake)
    error = ValueError("boom")

    obs.capture_exception(error, distinct_id="radar:1", properties={"job": "digest"})

    (sent,) = fake.exceptions
    assert sent["exception"] is error
    assert sent["distinct_id"] == "radar:1"
    assert sent["properties"] == {"job": "digest", "app_name": "radar", "environment": "production"}


def test_disabled_instance_does_not_capture_exceptions():
    Observability(app_name="radar", environment="production", client=None).capture_exception(
        ValueError("x"), distinct_id=None, properties={}
    )


def test_init_turns_on_process_level_autocapture_without_local_variables(monkeypatch):
    created = {}

    class RecordingPosthog:
        def __init__(self, token, **kwargs):
            created.update(kwargs, token=token)

    monkeypatch.setattr("posthog.Posthog", RecordingPosthog)

    init(app_name="radar", token="phc_test")

    assert created["enable_exception_autocapture"] is True
    assert created["capture_exception_code_variables"] is False


def make_app(obs):
    app = FastAPI()
    app.add_middleware(RequestEventsMiddleware, obs=obs)

    @app.get("/api/items/{item_id}")
    async def item(item_id: int, request: Request):
        set_user(request, 9)
        raise RuntimeError("database exploded")

    @app.get("/api/missing")
    async def missing():
        raise HTTPException(404, "nope")

    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_request_exception_goes_to_error_tracking_with_request_context(fake):
    obs = Observability(app_name="radar", environment="production", client=fake)

    make_app(obs).get("/api/items/3", headers={"X-POSTHOG-SESSION-ID": "sess-9"})

    (sent,) = fake.exceptions
    assert isinstance(sent["exception"], RuntimeError)
    assert sent["distinct_id"] == "radar:9"
    props = sent["properties"]
    assert (props["route"], props["method"], props["$session_id"], props["user_id"]) == (
        "/api/items/{item_id}",
        "GET",
        "sess-9",
        "radar:9",
    )
    # the api_request event itself still carries only the exception type
    assert "database exploded" not in repr(fake.events)


def test_handled_http_errors_are_not_reported_as_exceptions(fake):
    obs = Observability(app_name="radar", environment="production", client=fake)

    make_app(obs).get("/api/missing")

    assert fake.exceptions == []


def test_exception_inside_a_job_is_reported_and_re_raised(fake):
    init(app_name="radar", client=fake)

    with pytest.raises(KeyError), job_context("analysis", user_id=4, trace_id="analysis-1"):
        raise KeyError("missing field")

    (sent,) = fake.exceptions
    assert isinstance(sent["exception"], KeyError)
    assert sent["distinct_id"] == "radar:4"
    assert sent["properties"]["job"] == "analysis"
    assert sent["properties"]["$ai_trace_id"] == "analysis-1"


def test_job_that_succeeds_reports_nothing(fake):
    init(app_name="radar", client=fake)

    with job_context("analysis"):
        pass

    assert fake.exceptions == []


def test_job_user_set_after_the_job_started_is_used_for_its_error(fake):
    init(app_name="radar", client=fake)

    with pytest.raises(ValueError), job_context("analysis") as ctx:
        ctx.user_id = "radar:late"
        raise ValueError("x")

    (sent,) = fake.exceptions
    assert sent["distinct_id"] == "radar:late"
    assert sent["properties"]["user_id"] == "radar:late"
