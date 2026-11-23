"""Record each LLM call as a PostHog `$ai_generation` event, so LLM analytics shows cost per app, user, route and job.

Provider-agnostic: call it after any chat-completion call, with the usage the provider returned.

    started = time.perf_counter()
    response = await http.post(...)
    usage = response.json()["usage"]
    record_generation(
        model=model, provider="groq",
        input_tokens=usage["prompt_tokens"], output_tokens=usage["completion_tokens"],
        latency_ms=(time.perf_counter() - started) * 1000,
        input_cost_usd=..., output_cost_usd=...,   # optional: omit to let PostHog price known models
    )

Prompts and outputs are never sent. Generations are never sampled, so cost totals stay exact.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from monke_observability import context, core

log = logging.getLogger("monke_observability.llm")

_MAX_ERROR_LEN = 500


def record_generation(
    *,
    model: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: float,
    input_cost_usd: float | None = None,
    output_cost_usd: float | None = None,
    http_status: int | None = None,
    error: str | None = None,
    trace_id: str | None = None,
    properties: dict[str, Any] | None = None,
    obs: core.Observability | None = None,
) -> None:
    """`error` must be a short, non-sensitive description (status, error code); never a prompt or an API key."""
    obs = obs or core.get()
    if obs is None or not obs.enabled:
        return
    ctx = context.current()

    props: dict[str, Any] = {
        **(properties or {}),
        "$ai_model": model,
        "$ai_provider": provider,
        "$ai_input_tokens": int(input_tokens),
        "$ai_output_tokens": int(output_tokens),
        "$ai_total_tokens": int(input_tokens) + int(output_tokens),
        # PostHog's generation-properties table documents $ai_latency in milliseconds; latency_ms
        # is sent as well so the unit is unambiguous in our own queries.
        "$ai_latency": round(float(latency_ms), 2),
        "latency_ms": round(float(latency_ms), 2),
        "$ai_trace_id": trace_id or (ctx.trace_id if ctx else None) or str(uuid.uuid4()),
    }
    if input_cost_usd is not None:
        props["$ai_input_cost_usd"] = float(input_cost_usd)
    if output_cost_usd is not None:
        props["$ai_output_cost_usd"] = float(output_cost_usd)
    if http_status is not None:
        props["$ai_http_status"] = int(http_status)
    if error is not None:
        props["$ai_is_error"] = True
        props["$ai_error"] = str(error)[:_MAX_ERROR_LEN]

    distinct_id = None
    if ctx is not None:
        distinct_id = ctx.distinct_id
        if ctx.user_id:
            props["user_id"] = ctx.user_id
        if ctx.job:
            props["job"] = ctx.job
        if ctx.route:
            props["route"] = ctx.route
        if ctx.session_id:
            props["$session_id"] = ctx.session_id

    try:
        obs.capture_ai("$ai_generation", distinct_id=distinct_id, properties=props)
    except Exception:
        # Telemetry must never fail the LLM call it describes.
        log.exception("monke-observability: failed to queue $ai_generation event")
