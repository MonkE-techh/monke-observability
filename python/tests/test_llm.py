from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from monke_observability import Observability, init
from monke_observability.context import job_context
from monke_observability.fastapi import RequestEventsMiddleware, set_user
from monke_observability.llm import record_generation


def test_generation_event_carries_model_tokens_cost_and_latency(fake):
    obs = Observability(app_name="radar", environment="production", client=fake)

    record_generation(
        model="llama-3.3-70b-versatile",
        provider="groq",
        input_tokens=1200,
        output_tokens=300,
        latency_ms=842.5,
        input_cost_usd=0.000708,
        output_cost_usd=0.000237,
        obs=obs,
    )

    assert fake.events == []
    (sent,) = fake.ai_events
    props = sent["properties"]
    assert sent["event"] == "$ai_generation"
    assert props["$ai_model"] == "llama-3.3-70b-versatile"
    assert props["$ai_provider"] == "groq"
    assert (props["$ai_input_tokens"], props["$ai_output_tokens"], props["$ai_total_tokens"]) == (1200, 300, 1500)
    assert props["$ai_latency"] == 842.5
    assert props["latency_ms"] == 842.5
    assert (props["$ai_input_cost_usd"], props["$ai_output_cost_usd"]) == (0.000708, 0.000237)
    assert props["$ai_trace_id"]
    assert props["app_name"] == "radar"


def test_costs_are_left_out_when_unknown_so_posthog_prices_the_model(fake):
    obs = Observability(app_name="radar", environment="production", client=fake)

    record_generation(model="gpt-4o-mini", provider="openai", input_tokens=10, output_tokens=5, latency_ms=100, obs=obs)

    props = fake.ai_events[0]["properties"]
    assert "$ai_input_cost_usd" not in props and "$ai_output_cost_usd" not in props


def test_failed_generation_is_marked_as_error_without_prompt_content(fake):
    obs = Observability(app_name="radar", environment="production", client=fake)

    record_generation(
        model="m",
        provider="groq",
        input_tokens=0,
        output_tokens=0,
        latency_ms=50,
        http_status=429,
        error="rate limited",
        obs=obs,
    )

    props = fake.ai_events[0]["properties"]
    assert props["$ai_is_error"] is True
    assert props["$ai_error"] == "rate limited"
    assert props["$ai_http_status"] == 429
    assert "$ai_input" not in props and "$ai_output_choices" not in props


def test_generation_inside_a_job_is_attributed_to_the_job_and_user(fake):
    init(app_name="radar", client=fake)

    with job_context("analysis", user_id=7, trace_id="analysis-123"):
        record_generation(model="m", provider="groq", input_tokens=1, output_tokens=1, latency_ms=1)
        record_generation(model="m", provider="groq", input_tokens=1, output_tokens=1, latency_ms=1)

    first, second = fake.ai_events
    assert first["distinct_id"] == "radar:7"
    assert first["properties"]["job"] == "analysis"
    assert first["properties"]["user_id"] == "radar:7"
    assert first["properties"]["$ai_trace_id"] == second["properties"]["$ai_trace_id"] == "analysis-123"


def test_generation_outside_any_context_is_personless(fake):
    init(app_name="radar", client=fake)

    record_generation(model="m", provider="groq", input_tokens=1, output_tokens=1, latency_ms=1)

    sent = fake.ai_events[0]
    assert sent["distinct_id"] is None
    assert sent["properties"]["$process_person_profile"] is False


def test_generation_during_a_request_inherits_route_user_and_session(fake):
    obs = init(app_name="radar", client=fake)
    app = FastAPI()
    app.add_middleware(RequestEventsMiddleware, obs=obs)

    @app.post("/api/briefs/{brief_id}")
    async def make_brief(brief_id: int, request: Request):
        set_user(request, 5)
        record_generation(model="m", provider="groq", input_tokens=1, output_tokens=1, latency_ms=1)
        return {}

    TestClient(app).post("/api/briefs/9", headers={"X-POSTHOG-SESSION-ID": "sess-1"})

    props = fake.ai_events[0]["properties"]
    assert fake.ai_events[0]["distinct_id"] == "radar:5"
    assert props["route"] == "/api/briefs/{brief_id}"
    assert props["$session_id"] == "sess-1"


def test_record_generation_before_init_does_nothing():
    import monke_observability.core as core

    core._current = None
    record_generation(model="m", provider="groq", input_tokens=1, output_tokens=1, latency_ms=1)
