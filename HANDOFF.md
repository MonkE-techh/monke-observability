# Handoff: centralized monitoring for Monk-E's Render apps

Written 2026-11-23 at the end of a planning discussion. Nothing has been built yet; this folder holds only this file.

**Start the new session with:** "Read `HANDOFF.md` in this folder and continue from *Next steps*."

---

## 1. Goal

One place to see, for each Monk-E app separately and across all apps:

- **Logs:** every API request (route, status, duration, user, session) and errors.
- **User analytics:** visitors, active users, sessions, location, device, what people click and use.
- **LLM usage:** cost per request, tokens and model, per app, user and route.
- **Peaks:** peak usage hours and days, request volume over time.
- **History:** graphs over 30–45 days (and longer).

Start with 5–6 apps; **the number of apps will grow**, so the design must make adding an app cheap.

## 2. Decisions made

| Topic | Decision |
|---|---|
| Analytics, logs, LLM cost | **PostHog**, one project for all apps, every event tagged with `app_name` |
| Deep LLM tracing | **Langfuse later**, alongside PostHog, only if needed (prompt versions, agent traces, evaluations) |
| Server health, CPU, memory, bandwidth | **Render's built-in metrics** only; no extra tool |
| Build-from-scratch dashboard | **Not now.** Optional later: a thin Monk-E-branded page that reads PostHog's query API, with no storage of our own |
| Instrumentation standard | OpenTelemetry for backend logs + one shared event schema, so the provider can be swapped later without re-instrumenting apps |
| Code home | This repo: `D:\CODIN PLAYGROUND\Monk-E\monke-observability` |
| Distribution | **Versioned packages** (not copied files), because the app count will grow: Python `monke-observability`, Node `@monke/observability` |

### Why PostHog (comparison done in the discussion)

| Need | PostHog | Grafana Cloud | Langfuse | Build it |
|---|---|---|---|---|
| Visitors, users, sessions, location, device | strong | weak | none | lots of work |
| Request counts, peak hours, errors | yes | strong | none | lots of work |
| LLM cost per request / user / app | built in | manual | strongest | price table to maintain |
| 30–45-day graphs on the free plan | yes (events kept 1 year) | no (14 days) | no (30 days) | yes, but we run storage |
| Setup and upkeep | low | medium | low | high |

Known PostHog weak spots: raw log search (logs are newer and short-lived on the free plan), deep LLM agent debugging (Langfuse is better), and data residency (choose the EU region if client data matters).

## 3. Free-plan facts (as checked on 2026-11-23; re-check the pricing pages before relying on them)

| Item | Free allowance | Retention |
|---|---|---|
| Product analytics events | ~1 million / month | **1 year** |
| LLM analytics events | 100,000 / month | **30 days** |
| Logs | 10 GB or 50 GB / month (sources disagree) | short (reported 14 days; no free custom retention) |
| Session recordings | 5,000 / month | not stated |
| Error tracking | free allowance (figure not confirmed) | — |
| Projects | **1** on the free plan, so all apps share it and use `app_name` | — |
| Billing | a spending limit can be set per product, so no surprise bill | — |

Comparison figures: Grafana Cloud free has 50 GB logs, 50 GB traces, 10k metric series, 14-day retention. Langfuse Hobby has 50k units a month (traces + observations + scores), 30 days, 2 users. Langfuse Core costs $29 a month.

## 4. Design

### 4.1 Getting 30–45-day graphs despite short log/LLM retention

1. **Record every API request as a PostHog analytics event** (kept 1 year), not only as a log. Logs are for digging into recent detail.
2. **Nightly rollup job:** query PostHog for yesterday's aggregates and write them back into PostHog as a few `daily_rollup` events per app per day (kept 1 year). No database of our own. Aggregates to include:
   - requests per route
   - errors (4xx / 5xx)
   - average and slowest response times
   - busiest hour
   - LLM cost and tokens per app and model
3. **Stay under ~1M events a month:**
   - skip health checks and polling routes (for example, Creator Curation's job-history page polls every few seconds)
   - set a sampling rate per app for high-traffic apps
   - set a PostHog billing limit

### 4.2 Event schema (one shape for every app)

API request event (also emitted as an OTel log):

```json
{
  "event_type": "api_request",
  "app_name": "creator-curation",
  "environment": "production",
  "method": "POST",
  "route": "/api/v1/creators/{creator_id}/refresh",
  "status_code": 200,
  "duration_ms": 842,
  "user_id": "creator-curation:42",
  "posthogDistinctId": "creator-curation:42",
  "sessionId": "<from X-POSTHOG-SESSION-ID>"
}
```

Rules:

- **Routes:** use the route *template* (`/users/{id}`), never a URL with IDs or query strings.
- **User IDs:** namespace them per app (`appname:123`) so users of different apps never merge.
- **Identity source:**
  - The server-side authenticated user ID wins.
  - `X-POSTHOG-DISTINCT-ID` and `X-POSTHOG-SESSION-ID` are only for linking logs to sessions, never for authorization.
  - CORS must allow those two headers.
- **Never log:** passwords, tokens, cookies, `Authorization` headers, API keys or sensitive request bodies.
- **LLM calls:** sent through one wrapper that records `$ai_generation` events, so PostHog LLM analytics computes the cost. Each event records:
  - app name
  - model
  - input and output tokens
  - latency
  - route
  - user

### 4.3 Planned repo layout

```
monke-observability/
  README.md        event schema, naming rules, add-an-app checklist
  apps.yaml        app registry: name, Render services, uses_llm, sample rate, expected traffic
  python/          package: FastAPI + Django request middleware, LLM wrapper, OTel log setup
  node/            package: Express + Next.js server middleware, LLM wrapper, OTel log setup
  web/             browser setup: posthog-js init, identify on login, reset on logout, app_name, tracing_headers
  rollup/          nightly rollup job + Render cron config (reads apps.yaml)
  dashboards/      shared dashboard template + script that creates a per-app dashboard via the PostHog API
  tests/
```

Growth features:

- **App registry:** `apps.yaml` lists every app, and the rollup job reads it.
- **Add-an-app script:** registers a new app and creates its PostHog dashboard from the shared template, and the "All apps" overview picks it up automatically.
- **Per-app settings:** each app has its own sampling rate and an expected-traffic estimate on the add-an-app checklist.

### 4.4 Dashboards

- **All apps — overview:** visitors, active users, pageviews, API requests, traffic over time, top endpoints, errors, latency, peak-hour heatmap, countries, recent logs.
- **One dashboard per app,** filtered by `app_name` / `service.name`.
- **Project timezone:** set to **Asia/Kolkata** so peak-hour charts use IST.
- **Log-based metrics:** `api.request.count`, `api.error.count`, `api.request.duration`. These are in alpha, with averages and totals only and no p95/p99.

## 5. Render inventory (from `render services`, read-only, 2026-11-23)

22 services, all running, in about 7 apps. Static sites produce **no request logs on Render**, so their analytics must come from the browser SDK.

| App | Repo | Services |
|---|---|---|
| Creator Curation | MonkE-techh/creatorCurration_monkE | `monke-creator-web` (static), `monke-creator-api` (Python, FastAPI) |
| Engagement Bot Checker | MonkE-techh/engagementAuthCalc | web (static), api (Docker, starter), worker (Docker, standard) |
| Keyword Radar | MonkE-techh/KeywordRadar | `radar-web` (Python), `radar-dashboard` (static), 5 cron jobs |
| Monk-E Workspace | MonkE-techh/Data | `monke-workspace` (Docker; deploys manually) |
| Campaign Dashboard | MonkE-techh/monkE-CampaignDashboard | static frontend, Python backend |
| Reckitt AI visibility | akshatsharma-lab/… (personal account) | 4 static sites, 2 Node services; deploy manually |
| Monk-E Reporting | akshatsharma-lab/monke-reporting | Docker, 1 CPU / 2 GB |

Known facts:

- **Creator Curation:** React + Vite frontend, FastAPI backend, Google sign-in, no LLM calls. Its local path is `D:\CODIN PLAYGROUND\Monk-E\creatorCurration_monkE`.
- **Every other app:** stack and LLM use not yet checked.
- **Render CLI:** installed on this machine and signed in.

## 6. Open questions (need the user)

1. **Distribution:** public or private repo?
   - **Public** (recommended): apps install from a git version tag with no Render setup. The code holds no secrets.
   - **Private:** every Render service needs a read-only GitHub token.
   - **PyPI and npm:** the alternative is to publish there.
2. **Which 5–6 apps first?** Suggested:
   - the five MonkE-techh apps above
   - optionally Monk-E Reporting
   - leave the Reckitt client sites out until the client contract is checked
3. **Local paths:** where those repos are cloned, or permission to clone them.
4. **PostHog project:**
   - The user creates it and picks the region (EU vs US).
   - They share the `phc_` project key, which is public and safe to share.
   - The rollup's personal API key is secret: it goes only into Render environment settings, never into chat or code.
5. **Pilot app:** pick one that **makes LLM calls** (Keyword Radar or Campaign Dashboard likely) to prove cost per request end to end. Creator Curation has no LLM calls.

## Progress (2026-11-23, second session)

- Open questions 1, 2, 3 and 5 answered and region chosen: public repo, the 4 cloned apps, pilot = Engagement Bot Checker, PostHog EU. Details and remaining questions in `docs/engineering/AGENT_WORK_LOG.md`.
- Steps 2–3 done (git initialised, nothing committed): `python/` and `web/` packages built and tested; `node/` deferred (no Node backends in the first batch). Next: step 4 (pilot).

## 7. Next steps

1. Get answers to the open questions above.
2. Initialise this repo (git) with the layout in 4.3. Create the GitHub repo only when the user says so.
3. Write the Python and Node packages, the browser setup and tests against the schema in 4.2.
4. Pilot on one LLM-using app:
   - frontend SDK, `identify` on login, `tracing_headers`
   - backend middleware
   - LLM wrapper
   - Render environment variables: `POSTHOG_PROJECT_TOKEN`, `POSTHOG_HOST`, `APP_NAME`, `APP_ENV`
5. Verify end to end in PostHog: a real user's session linked to its API events, and an LLM call showing its cost.
6. Build the overview dashboard and the per-app template. Add the nightly rollup.
7. Roll out to the remaining apps with the add-an-app script.

## 8. Working rules from the user (apply to this repo too)

- **No AI attribution:** never credit an AI anywhere (commits, PRs, docs).
- **Ask before consequential changes,** keep diffs small, and keep `docs/engineering/AGENT_WORK_LOG.md` and `AGENT_ERROR_LOG.md` up to date.
- **Ask before outward-facing actions:** creating GitHub repos, deploying, changing Render settings.
- **Never print or commit secrets.**

## Sources

- https://posthog.com/pricing
- https://posthog.com/llm-analytics/pricing
- https://posthog.com/ai-observability/pricing
- https://posthog.com/docs/llm-analytics/start-here
- https://posthog.com/blog/events-data-retention-update
- https://posthog.com/session-replay/pricing
- https://dev.to/beton/posthog-pricing-teardown-2026-57oo
- https://langfuse.com/pricing
- https://langfuse.com/docs/administration/billable-units.md
- https://grafana.com/products/cloud/free-tier
- https://grafana.com/pricing/
