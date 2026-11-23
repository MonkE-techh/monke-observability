# monke-observability

Shared instrumentation that sends every Monk-E app's API requests, LLM usage, browser analytics and logs to **one PostHog project** (EU region), with each event tagged by `app_name`.

| Folder | What it is | Status |
|---|---|---|
| `python/` | `monke-observability` Python package: FastAPI/Starlette request middleware, LLM recorder, optional OTel log export | 0.1.0, tested |
| `web/` | `@monke/observability-web`: posthog-js setup (app tagging, identify/reset, tracing headers) | 0.1.0, tested |
| `apps.yaml` | Registry of every app (name, Render services, LLM use, sample rate) | first 4 apps |
| `admin/` | Internal Monk-E admin page that reads PostHog (see `admin/README.md`) | 0.1.0, tested locally with sample data |
| `rollup/` | Nightly job that writes `daily_rollup` events (keeps 30–45-day graphs) | not built yet |
| `dashboards/` | Shared dashboard template + per-app dashboard script | not built yet |
| `node/` | Express / Next.js server package | deferred: no app in the first batch has a Node backend |

Server health (CPU, memory, bandwidth) stays in Render's built-in metrics.

## Event schema

### `api_request` (one per API request, also logged on `monke_observability.request`)

| Property | Example | Notes |
|---|---|---|
| `app_name` | `creator-curation` | from `APP_NAME`; kebab-case; never rename |
| `environment` | `production` | from `APP_ENV` |
| `method` | `POST` | |
| `route` | `/api/v1/creators/{creator_id}/refresh` | route **template**; `unmatched` when no route matched; never the raw URL or query |
| `status_code` / `status_class` | `200` / `2xx` | an unhandled exception is `500` |
| `duration_ms` | `842.1` | |
| `user_id` | `creator-curation:42` | only when the server authenticated a user |
| `$session_id` | browser session id | from `X-POSTHOG-SESSION-ID`; links the request to the session replay |
| `error_type` | `RuntimeError` | exception class only, never its message |
| `sample_rate` | `1.0` | multiply counts by `1 / sample_rate` when sampled |

The event's `distinct_id` is the server-authenticated `user_id`; otherwise the browser's `X-POSTHOG-DISTINCT-ID`; otherwise none (personless event).

### `$ai_generation` (one per LLM call, never sampled)

`$ai_model`, `$ai_provider`, `$ai_input_tokens`, `$ai_output_tokens`, `$ai_total_tokens`, `$ai_latency` and `latency_ms` (milliseconds), `$ai_trace_id`, optional `$ai_input_cost_usd` / `$ai_output_cost_usd` (otherwise PostHog prices known models), `$ai_is_error` / `$ai_error` / `$ai_http_status` on failure, plus `app_name`, `environment`, and from the current context `user_id`, `route`, `job`, `$session_id`. Prompts and outputs are never sent.

### Browser events

posthog-js autocapture, pageviews (including client-side navigation) and session replay, with `app_name` and `environment` registered on every event.

## Rules

- **User ids are namespaced per app** (`appname:123`), in the browser and on the server, so users of different apps never merge.
- **The server-side authenticated user wins.** The `X-POSTHOG-*` headers only link events to sessions; they are validated, length-limited and never used for authorization.
- **CORS must allow** `X-POSTHOG-DISTINCT-ID` and `X-POSTHOG-SESSION-ID` (`TRACING_HEADERS` in the Python package).
- **Never sent:** request/response bodies, query strings, headers other than the two above, cookies, `Authorization`, passwords, tokens, API keys, prompts, local variable values.
- **Error Tracking (decided 2026-11-23):** unhandled exceptions are sent as PostHog `$exception` events **with message and stack trace**, from request handlers (middleware), background jobs (`job_context`), uncaught process errors (SDK autocapture) and the browser (`capture_exceptions`). Don't put secrets or personal data in exception messages. The `api_request` event and request log keep only the exception type.
- **Not recorded:** `OPTIONS`/`HEAD`, health checks (`/`, `/health`, `/healthz`, `/api/health`, `/api/healthz`), and any route passed in `exclude_routes` (use it for polling routes). Errors (5xx) are always kept; other requests are sampled by `MONKE_SAMPLE_RATE`.
- **Telemetry never breaks the app:** with no token everything is a no-op; capture failures are logged, not raised.

## Environment variables (Render)

| Variable | Value | Secret? |
|---|---|---|
| `APP_NAME` | the app's name from `apps.yaml` | no |
| `APP_ENV` | `production` / `staging` | no |
| `POSTHOG_PROJECT_TOKEN` | `phc_…` project token | no (public), but keep it in env, not code |
| `POSTHOG_HOST` | `https://eu.i.posthog.com` (default) | no |
| `MONKE_SAMPLE_RATE` | `1.0` (default), e.g. `0.2` for high-traffic apps | no |
| `VITE_POSTHOG_PROJECT_TOKEN` | same `phc_…`, for static frontends at build time | no |

The **personal API key** (`phx_…`) used by the admin page and the rollup job is secret: Render environment only, never in code, chat or logs. Step-by-step setup with links: `docs/SETUP_LINKS.md`.

## Python usage (FastAPI)

```python
from fastapi.middleware.cors import CORSMiddleware
from monke_observability import init
from monke_observability.fastapi import TRACING_HEADERS, RequestEventsMiddleware, set_user

init()  # APP_NAME, APP_ENV, POSTHOG_PROJECT_TOKEN, POSTHOG_HOST, MONKE_SAMPLE_RATE

app.add_middleware(RequestEventsMiddleware, exclude_routes={"/api/jobs/{job_id}/status"})
app.add_middleware(CORSMiddleware, allow_headers=["Content-Type", *TRACING_HEADERS], ...)

async def require_user(request: Request) -> User:
    user = ...                    # existing authentication, unchanged
    set_user(request, user.id)
    return user
```

Add `RequestEventsMiddleware` **before** `CORSMiddleware` in code (so CORS stays outermost and preflights are answered as before).

LLM calls, inside a request or a background job:

```python
from monke_observability.context import job_context
from monke_observability.llm import record_generation

# worker: once per job, so generations are attributed to the job and the user who started it
with job_context("analysis", user_id=analysis.created_by, trace_id=f"analysis-{analysis.id}"):
    ...

# after each chat-completion call
record_generation(model=model, provider="groq", input_tokens=pt, output_tokens=ct, latency_ms=ms,
                  input_cost_usd=in_cost, output_cost_usd=out_cost)
```

Workers are separate processes: call `init()` at worker start-up and `get().flush()` at shutdown.

Optional log export to PostHog Logs (`monke-observability[otel]`): `setup_otel_logs(init())`.

## Browser usage

See the comment at the top of `web/src/index.ts`. `apiHosts` lists the app's API hostnames so posthog-js adds the tracing headers to those requests only.

## Installing in an app

Python (uv), pinned to a release tag:

```
uv add "monke-observability @ git+https://github.com/<org>/monke-observability@v0.1.0#subdirectory=python"
```

The Docker images must have `git` available at build time for this. Browser package: npm cannot install from a subfolder of a git repo, so the release process must publish `web/` another way (see open question in `docs/engineering/AGENT_WORK_LOG.md`).

## Add an app

1. Add it to `apps.yaml` (name, repo, Render services, `uses_llm`, `sample_rate`, expected daily requests).
2. Check the expected traffic against the ~1M events/month free allowance; lower `sample_rate` or exclude polling routes if needed.
3. Backend: install the package, add the middleware and `set_user` call, allow the tracing headers in CORS, wrap LLM calls with `record_generation`.
4. Frontend: install the web package, call `initAnalytics`, `identify` after sign-in, `reset` on sign-out.
5. Set the Render environment variables above on every service of the app.
6. Create the app's dashboard (script in `dashboards/`, once built).

## Development

```
cd python && uv sync --all-extras && uv run pytest && uv run ruff check .
cd web && npm install && npm test && npm run typecheck && npm run build
```
