# Monk-E admin page — design

Date: 2026-11-23 · Status: draft, awaiting approval

## Why

All Monk-E apps send their analytics, API requests and LLM usage to one PostHog project (EU) through the `monke-observability` packages. The tech team wants **one Monk-E page** that answers, for every app at once and for each app alone, "is it healthy, how much is it used, when, and what do the LLM calls cost?" — without opening PostHog. PostHog stays the place to dig deeper.

## Audience

Only the user and the tech team. Internal tool: plain, dense, accurate; no client views, no marketing polish.

## Goals

- One overview of all apps, and one page per app, for a chosen range (7 / 30 / 45 / 90 days).
- Numbers that match PostHog (same events, sampling corrected).
- Adding an app needs no admin code change: it appears from `apps.yaml` (and from data, flagged as unregistered).
- The PostHog personal API key never reaches the browser.

## Non-goals (v1)

- Storing data of our own. The page only reads PostHog.
- The nightly rollup job (separate HANDOFF step 6). Until it exists, LLM figures older than 30 days are not available (PostHog keeps LLM events 30 days); the page says so instead of showing zeros.
- Raw log search, session replay viewer, editing PostHog dashboards. Each panel links to PostHog instead.
- Alerts / notifications.
- Client or per-person access levels.

## Anti-goals

- A number that looks fine because a query failed (empty ≠ zero). Every panel shows its own error or "no data yet".
- Hammering PostHog's query API (3 concurrent queries, 10 s per query, 2400/hour per project).
- Anyone outside the allow-list seeing the page.

## Approaches considered

| | Approach | Trade-off |
|---|---|---|
| **A (chosen)** | Standalone small app: FastAPI backend holds the key and queries PostHog; React page; Google sign-in with an email allow-list; one Render service | One more service; independent of every app; scales with `apps.yaml` |
| B | Tab inside an existing app's admin area | No new service, but the cross-app view depends on one unrelated app |
| C | Static page embedding PostHog shared dashboards | Almost no code, but shared links are public URLs and charts can't be shaped |

User picked A on 2026-11-23.

## Design

### Shape

```
admin/
  backend/   FastAPI app (Python 3.12+, uv): auth, /api/* JSON, serves the built frontend
  frontend/  React + Vite + TypeScript, built into backend's static folder
```

One Render web service; the frontend is served by FastAPI from the same origin, so no CORS. Reads `apps.yaml` from the repo at start-up.

### Sign-in (follows Engagement Bot Checker's `app/core/auth.py` pattern)

- Google OAuth code flow; signed, HttpOnly, Secure, SameSite=Lax session cookie (HMAC with `SESSION_SECRET`, ≥32 chars), 12-hour expiry.
- Access only if the verified Google email is in `ADMIN_EMAILS` (comma-separated). *Builder's call:* optional `GOOGLE_WORKSPACE_DOMAIN` additionally requires the `hd` claim.
- Every `/api/*` route except `/api/auth/*` and `/api/health` requires the session. Unauthenticated page loads show a "Sign in with Google" screen; a signed-in but not allowed email gets "Not on the access list"; the refusal is logged without the email address.
- `AUTH_DISABLED=true` for local development only, refused when `APP_ENV=production`.

### Data access

- `POST {POSTHOG_APP_HOST}/api/projects/{POSTHOG_PROJECT_ID}/query` with `{"query": {"kind": "HogQLQuery", "query": …}}`, `Authorization: Bearer {POSTHOG_PERSONAL_API_KEY}`. The key needs only the **query:read** scope.
- All queries live in one backend module, built from fixed templates; the only inputs are the range (whitelisted: 7/30/45/90) and the app name (must match `^[a-z0-9]+(-[a-z0-9]+)*$` and come from `apps.yaml` or the app list query). Pass it as a HogQL placeholder (`values` on the HogQLQuery — builder to confirm against PostHog's docs); the strict pattern is the guarantee either way.
- Times shown in **Asia/Kolkata** (`toTimeZone(timestamp, 'Asia/Kolkata')`).
- Request counts are sampling-corrected: `sum(1 / coalesce(toFloat(properties.sample_rate), 1))`.
- At most 3 PostHog queries in flight (semaphore); 15 s HTTP timeout; results cached in memory for 5 minutes per (query, range, app). A "Refresh" button bypasses the cache for that page, at most once a minute.
- Each panel's endpoint returns either data, `{"error": "posthog_unavailable" | "posthog_timeout" | "not_configured"}`, or an explicit empty result; the UI renders each case differently.

### Screens

**Overview (all apps)**

```
Monk-E admin                         [7d] [30d] [45d] [90d]   Refresh · you@monk-e.in
┌ API requests ┐┌ 5xx error rate ┐┌ Avg response ┐┌ Visitors ┐┌ LLM cost (USD) ┐
└──────────────┘└────────────────┘└──────────────┘└──────────┘└────────────────┘
Requests per day, stacked by app                       Peak hours (IST): weekday × hour heatmap
Apps
 app                  requests  errors%  avg ms  slowest ms  visitors  LLM $   last event
 engagement-bot-check   12,410    0.4%     310      9,120       85    3.12   2 min ago
 keyword-radar           …                                                       ⚠ 26 h ago
 (unregistered) foo      …
```

- "Last event" older than 24 h is flagged (catches an app whose instrumentation broke).
- LLM tile and column for ranges > 30 days show the last-30-day value with a "LLM history: 30 days" note.

**App page** (click an app)

- Same tiles for that app; requests per day; peak-hours heatmap.
- Top routes: route, requests, error %, avg ms, slowest ms (top 20 by requests).
- Recent server errors: last 50 `api_request` with status ≥ 500 — time (IST), method, route, status, `error_type`, user id; each links to the event in PostHog.
- LLM: cost and tokens by model; cost by job / route; calls with `$ai_is_error`; top 10 users by LLM cost (internal page, ids only).
- Visitors: countries, device types, browsers (from browser events' GeoIP / `$device_type`).
- "Open in PostHog" link per section.

**States:** first run with no PostHog settings → setup screen listing the missing env vars (names only); app with no events in range → "No events from this app in the selected range" with the install checklist link; panel error → message plus retry.

### Configuration (Render env)

| Variable | Secret |
|---|---|
| `POSTHOG_PERSONAL_API_KEY` (query:read only) | **yes** |
| `POSTHOG_PROJECT_ID`, `POSTHOG_APP_HOST` (default `https://eu.posthog.com`) | no |
| `GOOGLE_CLIENT_ID` | no |
| `GOOGLE_CLIENT_SECRET`, `SESSION_SECRET` | **yes** |
| `ADMIN_EMAILS`, optional `GOOGLE_WORKSPACE_DOMAIN`, `APP_ENV` | no |

Secrets are never logged, returned by the API, or committed; `.env.example` lists names only.

### Testing

- Backend (pytest): query builders (range/app validation, placeholders, sampling formula), PostHog client with a fake transport (success, 4xx, timeout, rate limit 429), cache and concurrency limit, auth (allow-list, bad/expired cookie, AUTH_DISABLED refused in production), each endpoint's data / empty / error shapes.
- Frontend (vitest): number and time formatting (IST), panel states.
- Manual: run locally against the real PostHog project once it exists; check the numbers against the same insight in PostHog; check the page at desktop and phone width.

## Left to the builder (marked as Claude's calls)

- Chart library: **Recharts** (common, React-native, enough for bars, lines and a heatmap grid).
- Visitors = unique `distinct_id` on `$pageview` events in range.
- "Slowest" = max `duration_ms`; no p95 in v1 (can be added with `quantile(0.95)` later).
- The admin service does not instrument itself (keeps its own traffic out of the numbers).
- Layout desktop-first, usable at phone width; light theme following system dark mode.

## Depends on / outward-facing steps (need the user's go-ahead at the time)

- PostHog project (EU) and a personal API key with query:read — created by the user.
- A Google OAuth client with the admin's redirect URL — created by the user (or reuse the Workspace's Google Cloud project).
- Creating the Render service and the public GitHub repo under MonkE-techh.
