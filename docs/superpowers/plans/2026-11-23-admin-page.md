# Monk-E admin page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** an internal page showing request, error, latency, visitor and LLM-cost figures for all Monk-E apps and per app, read from PostHog.

**Architecture:** `admin/backend` (FastAPI) holds the PostHog personal key, runs fixed HogQL templates through a concurrency-limited, cached client, and serves `/api/*` plus the built `admin/frontend` (React + Vite + Recharts) from one origin. Google sign-in with an email allow-list guards everything except health and auth routes.

**Tech Stack:** Python 3.12+, uv, FastAPI, httpx, PyYAML, pytest · React 18, Vite, TypeScript, Recharts, vitest · Docker for Render.

**Spec:** `docs/superpowers/specs/2026-11-23-admin-page-design.md`

## Global Constraints

- Ranges: only 7, 30, 45, 90 days. Times in `Asia/Kolkata`.
- App names must match `^[a-z0-9]+(-[a-z0-9]+)*$`; days are ints from the whitelist; these are the only values interpolated into HogQL.
- Request weight: `if(toInt(properties.status_code) >= 500, 1, 1 / coalesce(toFloat(properties.sample_rate), 1))` (5xx are never sampled).
- LLM cost per event: `coalesce(toFloat(properties.$ai_total_cost_usd), toFloat(properties.$ai_input_cost_usd) + toFloat(properties.$ai_output_cost_usd), 0)`.
- PostHog: ≤3 queries in flight, 15 s timeout, 5-minute cache, manual refresh at most once a minute per page.
- Panel shape: `{"status": "ok", "data": …}` | `{"status": "empty"}` | `{"status": "error", "error": "posthog_unavailable" | "posthog_timeout" | "posthog_rate_limited" | "not_configured"}`.
- Secrets (`POSTHOG_PERSONAL_API_KEY`, `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET`) never logged, returned or committed.
- Session cookie: HMAC-signed, HttpOnly, Secure (except local http), SameSite=Lax, 12 h.

## Review Focus

1. Sampled app: request counts must be scaled, error counts must not be (test in Task 3).
2. Registered app with no events in range must still appear, flagged, not vanish (Task 3).
3. PostHog 429 / timeout / 5xx must surface as a panel error, never as zeros (Tasks 2, 3).
4. Forged, expired or tampered session cookie → 401 (Task 4).
5. Unknown app name or range in the URL → 404 / 422, never reaches HogQL (Task 5).

---

### Task 1: settings and registry
**Files:** `admin/backend/pyproject.toml`, `src/monke_admin/{__init__,settings,registry}.py`, `tests/test_settings.py`, `tests/test_registry.py`
**Produces:** `Settings.from_env() -> Settings` (fields: posthog_api_key, posthog_project_id, posthog_app_host="https://eu.posthog.com", google_client_id, google_client_secret, session_secret, admin_emails: frozenset[str], workspace_domain, public_url, app_env="production", auth_disabled, apps_file); `Settings.missing() -> list[str]` (env var names only); `load_registry(path) -> list[AppEntry(name, uses_llm, status)]`; `valid_app_name(str) -> bool`.
- [ ] Tests: missing() lists absent names; admin emails lower-cased/trimmed; AUTH_DISABLED with APP_ENV=production raises; registry parses `apps.yaml`, rejects bad names.
- [ ] Red, implement, green.

### Task 2: PostHog query client and cache
**Files:** `src/monke_admin/posthog.py`, `src/monke_admin/cache.py`, tests
**Produces:** `QueryClient(settings, transport=None)`, `async run(sql: str, name: str) -> list[dict]` (rows keyed by `columns`); raises `QueryError(code)`; `TTLCache.get_or_compute(key, fn, force=False)`.
- [ ] Tests (httpx.MockTransport): body is `{"query": {"kind": "HogQLQuery", "query": …}, "name": …}` with Bearer key; 429→`posthog_rate_limited`; timeout→`posthog_timeout`; 5xx/invalid JSON→`posthog_unavailable`; not configured→`not_configured`; at most 3 concurrent; cache hit within TTL, miss after, `force` bypasses; failures not cached.

### Task 3: queries and panels
**Files:** `src/monke_admin/queries.py`, `src/monke_admin/panels.py`, tests
**Produces:** `overview(client, days) -> dict[str, Panel]` keys `tiles, daily, heatmap, apps`; `app_detail(client, app, days) -> dict[str, Panel]` keys `tiles, daily, heatmap, routes, errors, llm_models, llm_sources, llm_users, visitors`.
- [ ] Tests with a fake client returning canned rows: SQL contains the weight and cost expressions, IST, interval; `apps` panel merges registry (missing app → zero row, `last_event: null`) and unregistered apps (`registered: false`); query failure → that panel error, others ok; empty rows → `empty`; invalid app/days raise ValueError.

### Task 4: auth
**Files:** `src/monke_admin/auth.py`, tests
**Produces:** `sign(payload, secret, purpose) / verify(...)`; `router` with `/api/auth/google/start`, `/callback`, `/me`, `/logout`; dependency `require_admin(request) -> str` (email).
- [ ] Tests: start sets a signed state cookie and redirects to Google with client_id, redirect_uri `{public_url}/api/auth/google/callback`, scope `openid email profile`; callback with mismatched state → redirect `/?auth=failed`; token exchange via MockTransport; email not in list → `/?auth=denied`; unverified email or wrong `aud`/`iss`/expired → denied; workspace domain mismatch → denied; success sets session cookie; tampered/expired cookie → 401; AUTH_DISABLED → `local@localhost`.

### Task 5: API and app factory
**Files:** `src/monke_admin/main.py`, tests
**Produces:** `create_app(settings=None, client=None) -> FastAPI`; routes `GET /api/health`, `GET /api/status` (`{configured, missing, posthog_links}`), `GET /api/overview?range=30&refresh=0`, `GET /api/apps/{name}?range=…`; static files + SPA fallback from `static/`.
- [ ] Tests: unauthenticated → 401; range outside whitelist → 422; unknown or invalid app → 404; refresh throttled to once a minute; status never includes secret values.

### Task 6: frontend
**Files:** `admin/frontend/*` (Vite React TS), `src/lib/format.ts` + tests, `src/api.ts`, `src/components/*`, `src/pages/{Overview,AppPage}.tsx`
- [ ] vitest for formatters (numbers, USD, ms, IST relative time, stale > 24 h) and `panelState`.
- [ ] Screens per spec; states: sign-in, denied, setup (missing vars), loading, panel error with retry, empty, LLM-30-day note.
- [ ] `npm run build` outputs to `admin/backend/static`.
- [ ] Browser check with `tests/fake_server.py` (fake client + AUTH_DISABLED) at 1280 px and 390 px; console clean.

### Task 7: packaging and docs
**Files:** `admin/Dockerfile`, `render.yaml` (not applied), `admin/README.md`, `.env.example`, root README row, `docs/SETUP_LINKS.md`
- [ ] `docker build` if Docker is available; otherwise record NOT RUN.
