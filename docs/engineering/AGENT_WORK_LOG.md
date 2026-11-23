# Agent work log

## [2026-11-23 16:25–16:40 IST] Task: initialise repo and build the Python + browser packages (HANDOFF steps 1–3)

- **User request / acceptance criteria:** continue from HANDOFF.md "Next steps": answer the open questions, initialise the repo with the planned layout, write the Python and browser packages with tests against the schema in HANDOFF 4.2.
- **Starting state:** folder held only `HANDOFF.md`; not a git repo.
- **Decisions from the user (asked 2026-11-23):**
  - Repo will be **public** (GitHub repo not created yet — needs the user's go-ahead and the org name).
  - First apps: the 4 cloned repos — Creator Curation, Engagement Bot Checker, Keyword Radar, Campaign Dashboard.
  - Pilot: **Engagement Bot Checker**.
  - PostHog region: **EU** (project not created yet; user to create it and share the `phc_` key).
- **Investigation (read-only, in the app repos):**
  - All four apps: React + Vite frontends, FastAPI backends, uv with lockfiles; `requires-python` 3.12–3.14.
  - LLM use: Engagement Bot Checker (Groq over httpx, already computes per-model cost in `app/llm/client.py`; calls run in the arq worker) and Keyword Radar (Groq/OpenRouter in `radar.agent`, run as CLI/cron). Campaign Dashboard and Creator Curation: no LLM calls found.
  - Engagement Bot Checker resolves the user in a dependency (`app/api/deps.py: require_user`), not in middleware; its CORS allows only `Content-Type`. Working tree clean, branch `phonePe-play-with-low-category`.
  - Keyword Radar has uncommitted changes on `main` (left untouched).
  - PostHog docs (via context7): Python `capture`/`capture_ai`, `$ai_generation` properties incl. pre-calculated costs and `$ai_is_error`/`$ai_error`, posthog-js `tracing_headers` (hostnames only), Logs OTLP endpoint `<host>/i/v1/logs` with `Bearer phc_…`.
- **Plan:** git init; registry + README; Python package (core, ASGI middleware, context, LLM recorder, optional OTel logs) and browser package, test-first.
- **Changes made:**
  - `.gitignore`, `apps.yaml` (4 apps; Render service names still TODO for 3), `README.md` (schema, rules, env vars, usage, add-an-app checklist).
  - `python/` — `monke-observability` 0.1.0: `core.py` (init from env, kebab-case app names, sample rate validation, no-op without token, `app:id` namespacing), `fastapi.py` (pure ASGI `RequestEventsMiddleware`, `set_user`, `TRACING_HEADERS`), `context.py` (per-request/per-job context, `job_context`), `llm.py` (`record_generation`), `logs.py` (optional OTel export to PostHog Logs).
  - `web/` — `@monke/observability-web` 0.1.0: `initAnalytics`, `identify` (namespaced), `reset` (re-registers app tags), hostname normalisation for `tracing_headers`; no runtime dependencies (posthog-js is a peer).
  - Deferred: `node/` (no Node backends in the first batch), `rollup/`, `dashboards/` (HANDOFF step 6).
- **Checks run:**
  - `uv run pytest -q` (python) — PASS, 40 passed, 1 warning (Starlette TestClient wants `httpx2`; see ERR-2).
  - `uv run ruff check .` / `uv run ruff format --check .` — PASS after formatting.
  - `uv build` — PASS, sdist + wheel built.
  - `npx vitest run` (web) — PASS, 9 passed. `npx tsc --noEmit` — PASS. `npm run build` — PASS.
  - Each test file was run red before its implementation (import errors / 9 failing tests), then green.
- **Errors:** ERR-1, ERR-2, ERR-3.
- **Open questions for the user:**
  1. GitHub org/owner for the public repo, and permission to create it and push.
  2. How to distribute the browser package: npm cannot install from a git subfolder. Options: (a) a `.tgz` attached to each GitHub release (no registry, recommended), (b) publish to npm, (c) move `web/` to its own repo.
  3. Pilot integration touches the Engagement Bot Checker repo: which branch to work on (current is `phonePe-play-with-low-category`), and confirmation its Docker images can have `git` at build time for the git dependency.
  4. PostHog project creation (EU) and the `phc_` key; project timezone Asia/Kolkata.
- **Remaining risks / unverified behavior:**
  - Nothing has been sent to a real PostHog project; all checks use a fake client.
  - `$ai_latency` unit: one PostHog docs page says milliseconds; we send ms plus an explicit `latency_ms`. Confirm in the PostHog LLM UI during the pilot.
  - OTel log export not exercised against a live endpoint; the SDK `LoggingHandler` is deprecated (ERR-3).
- **Outcome:** PARTIAL — steps 1 (except PostHog key) to 3 done; steps 4–7 blocked on the open questions above. Nothing committed (not asked).

## [2026-11-23] Decisions: admin page and distribution (answers to the open questions above)

- **Admin page:** user chose PostHog for collection **plus one Monk-E admin page** that reads PostHog (option b). Audience: **only the user / tech team** (internal health and cost page). Approach not chosen yet.
- **GitHub:** public repo under **MonkE-techh**; user allowed creating it and pushing once code is ready (not done yet).
- **Distribution:** **GitHub release files** — each release attaches the Python wheel and the browser `.tgz`; apps install from those URLs. Reason: the pilot's backend image (`python:3.14-slim`) has no `git`, so git-tag installs would fail.
- **Pilot branch:** new branch off `main` in Engagement Bot Checker (e.g. `feature/observability`), independent of `phonePe-play-with-low-category`.
- **Still needed from the user:** PostHog project (EU, timezone Asia/Kolkata) and its `phc_` key.

## [2026-11-23 16:50–17:20 IST] Task: build the Monk-E admin page (design approved by the user)

- **User request / acceptance criteria:** "go ahead and build this" (design `docs/superpowers/specs/2026-11-23-admin-page-design.md`, approach A) and "give links for what is needed from my side".
- **Plan:** `docs/superpowers/plans/2026-11-23-admin-page.md` (7 tasks), executed inline, test-first.
- **Changes made:**
  - `admin/backend/` — FastAPI app `monke_admin`: `settings.py` (env, missing-variable names only, AUTH_DISABLED refused in production), `registry.py` (apps.yaml), `posthog.py` (HogQL query client: ≤3 concurrent, 15 s timeout, errors mapped to safe codes), `cache.py` (5-minute TTL, failures not cached), `queries.py` (fixed templates; sampling-corrected counts, 5xx unweighted, IST buckets, whitelisted ranges, validated app names), `panels.py` (per-panel ok/empty/error; registry merge), `auth.py` (Google OAuth, signed state + session cookies, email allow-list re-checked per request, optional Workspace domain), `main.py` (API, refresh throttle, SPA serving). `tests/fake_server.py` — local preview with made-up data (test tooling, not deployed).
  - `admin/frontend/` — React 19 + Vite + Recharts: overview and per-app pages, setup / sign-in / denied / failure states, panel error with retry, LLM 30-day note, IST times, Indian digit grouping.
  - `admin/Dockerfile`, `.dockerignore`, `render.yaml` (Blueprint, not applied), `admin/.env.example`, `admin/README.md`, `docs/SETUP_LINKS.md` (user-side steps and links), root README rows, `.gitignore` (build output, agent scratch).
- **Checks run:**
  - `uv run pytest -q` (admin/backend) — PASS, 81 passed. `uv run ruff check .` / `ruff format --check` — PASS.
  - `npx vitest run` (admin/frontend) — PASS, 9 passed. `npm run build` (tsc + vite) — PASS; warning: bundle > 500 kB (Recharts).
  - Regression of earlier packages: python 40 passed; web 9 passed.
  - Browser (agent-browser, Edge/Chromium; fake data, sign-in off): overview and app page at 1280 px, overview at 390 px (no horizontal overflow, `scrollWidth` 390), light and dark schemes, console clean — PASS. Sign-in, denied and setup screens were not viewed in the browser (covered by API tests only).
  - `docker build` — NOT RUN: Docker is not installed on this machine (ERR-8).
- **Errors:** ERR-4 to ERR-8.
- **Self-review:** done by the author (no separate reviewer requested). Found and fixed: Docker build context would have copied local `.venv`/`node_modules`/build output (added `.dockerignore`).
- **Remaining risks / unverified behavior:**
  - **No query has run against real PostHog.** HogQL functions and property paths (`toInt(properties.status_code)`, `toDayOfWeek`, `$ai_total_cost_usd`, `$geoip_country_name`) follow ClickHouse/HogQL conventions but are unverified until the project exists.
  - Google sign-in tested with a mocked token endpoint only.
  - Render free plan sleeps when idle (first load slow; in-memory cache lost).
  - Nothing committed or pushed; GitHub repo and Render service not created.
- **Outcome:** COMPLETE for local build and tests; deployment BLOCKED on the user-side steps in `docs/SETUP_LINKS.md`.

## [2026-11-23 17:35 IST] Task: send crashes to PostHog Error Tracking

- **User decision (asked 2026-11-23):** user enabled Metrics and Error Tracking in PostHog; chose "Yes, backend + browser" for sending exceptions **with messages and stack traces**, relaxing the earlier "never send exception messages" rule. Local variable values stay off.
- **Also discussed:** UptimeRobot ping on `/api/health` every 5 min to keep the free Render service awake (750 free hours/month per workspace caveat) — added to `docs/SETUP_LINKS.md` and `admin/README.md`. PostHog products recommended: Product Analytics, Web Analytics, Session Replay, AI observability, Logs (+ Error Tracking now). Metrics: nothing sends to it yet (no change).
- **Changes made:**
  - `python/src/monke_observability/core.py` — `Observability.capture_exception()`; `init()` turns on SDK exception autocapture with `capture_exception_code_variables=False`.
  - `python/src/monke_observability/fastapi.py` — unhandled request exceptions reported with route, method, user, session (`api_request` unchanged: type only).
  - `python/src/monke_observability/context.py` — `job_context` reports exceptions raised in a job, then re-raises.
  - `web/src/index.ts` — `capture_exceptions: true`.
  - `README.md` — privacy rules updated.
- **Checks run:** `uv run pytest -q` (python) — PASS, 47 passed (7 new in `tests/test_errors.py`; 5 failed first, the 2 "nothing reported" guards passed before and after). `ruff check` / `format` — PASS. `npx vitest run` (web) — PASS, 10 passed (new test failed first). `tsc --noEmit`, `npm run build` — PASS.
- **Remaining risks:** not verified against a live PostHog project; React render errors reach `window.onerror` only when not caught by an error boundary.
- **Outcome:** COMPLETE (local).

## [2026-11-23 17:45 IST] Task: admin page environment switch (production by default)

- **User decision (asked 2026-11-23):** pilot runs locally first (no Render yet); local events share the PostHog project tagged `environment=development`. User chose "Production + switch".
- **Answered:** where the `phc_` token goes for local work — Engagement Bot Checker `backend/.env` (or repo-root `.env`, loaded by its pydantic-settings) with `APP_ENV=development`, and `frontend/.env.local` as `VITE_POSTHOG_PROJECT_TOKEN`. Noted for the pilot: pydantic-settings does not export `.env` into `os.environ`, so the pilot must pass settings to `init()` explicitly. Pilot branch will live in a separate git worktree so the user's current checkout is untouched.
- **Changes made:**
  - `admin/backend/src/monke_admin/queries.py` — `ENVIRONMENTS = ("production", "development")`; every template filters `properties.environment`, validated before use.
  - `admin/backend/src/monke_admin/panels.py`, `main.py` — `env` threaded through; `?env=` (default production, 422 otherwise); response echoes `environment`; refresh throttle keyed per env; `/api/meta` lists environments.
  - `admin/frontend/src/{App.tsx,api.ts,pages/*.tsx,styles.css}` — Production / Development switch in the top bar (kept in the URL), development banner, env carried through links.
- **Checks run:** `uv run pytest -q` (admin/backend) — PASS, 89 passed (8 new, failed first). `ruff check` / `format` — PASS. Frontend `tsc --noEmit`, `vitest` (9) and `vite build` — PASS. Browser (fake data): development mode at 1280 px and 390 px, no overflow, console clean — PASS.
- **Remaining risks:** apps with `APP_ENV=staging` (or anything other than production/development) are not shown; the Python package defaults to `production` when `APP_ENV` is unset, so local runs must set `APP_ENV=development`.
- **Outcome:** COMPLETE (local).

## [2026-11-23 18:30 IST] Task: first commit and push to GitHub

- **User request:** commit the repo (it had no commits) and push it.
- **Before committing:** checked that `.env` files (`admin/backend/.env`, `admin/frontend/.env.local`) are git-ignored; scanned the 72 files for tokens, keys and private keys (none; only the team test address in fixtures).
- **Checks run:** `python`: pytest 51 passed, ruff PASS. `admin/backend`: pytest 89 passed. `web`: vitest 11 passed. `admin/frontend`: vitest 9 passed.
- **Outcome:** committed locally; push depends on the GitHub repository existing (see the final report).

## [2026-11-23 18:15 IST] Task: pilot in Engagement Bot Checker (local development)

- **User decisions:** token copied into Engagement Bot Checker's git-ignored `backend/.env` (`APP_ENV=development`) and `frontend/.env.local` (the user had first put it under `monke-observability/admin/`); pilot approved; **user id = hashed email** (`sha256(trimmed lower-case email)[:16]`, namespaced per app), not the email.
- **Where:** git worktree `D:\CODIN PLAYGROUND\Monk-E\Engagement Authenticity Calculator-observability`, branch `feature/observability` from `origin/main` (a5d73bb). The user's checkout on `phonePe-play-with-low-category` untouched. Nothing committed.
- **monke-observability changes found necessary during the pilot:**
  - `pseudonymous_id` (Python) / `pseudonymousId` (web), same test vector in both suites.
  - `job_context` now reports errors with the user known at failure time (set after the job started).
  - **Route template bug:** FastAPI 0.162+ reports `include_router(prefix=...)` routes without the prefix (`/auth/me` instead of `/api/auth/me`); `route_template` now rebuilds the full template from the path and path params, falling back to the route's own template if the prefix would contain an id (ERR-9).
- **Pilot changes (worktree):**
  - `backend/pyproject.toml`, `uv.lock` — `monke-observability` as an **editable local path** source (temporary; switch to the GitHub release wheel before merging, Docker build will not work with a path source).
  - `backend/app/core/config.py` — `POSTHOG_PROJECT_TOKEN` (secret type), `POSTHOG_HOST` (EU default), `APP_ENV`.
  - `backend/app/core/observability.py` (new) — `setup()`, `user_key()` (hashed email).
  - `backend/app/main.py` — `setup` in lifespan, flush on shutdown, `RequestEventsMiddleware` inside CORS, CORS allows the two tracing headers.
  - `backend/app/api/deps.py` — `set_user(request, user_key(email))`.
  - `backend/app/worker.py` — setup/flush; `job_context` for analysis (`analysis-<id>` trace), pricing, snapshot, retention, sweep jobs.
  - `backend/app/llm/client.py` — `record_generation` after each successful Groq call (model, tokens, latency, cost from the app's own price table; no prompt, no key).
  - `frontend/package.json`, `package-lock.json` — `posthog-js`, `@monke/observability-web` (`file:` link, temporary).
  - `frontend/src/analytics.ts` (new), `frontend/src/api/hooks.ts` — init (off in test mode), identify by hashed email after `/auth/me`, reset after sign-out.
  - Tests: `backend/tests/test_observability.py` (7), `frontend/src/test/analytics.test.ts` (5).
- **Checks run:**
  - Baseline before changes: backend `pytest -m "not db"` 306 passed (63 db tests deselected); frontend 156 passed, build OK.
  - After: backend 313 passed; `ruff check app tests` PASS; `mypy` on the 7 changed files PASS (it caught ERR-10). Repo-wide `ruff check .` shows 40 pre-existing findings in `alembic/versions/` (untouched).
  - Frontend: 161 passed; oxlint clean on changed files (2 pre-existing warnings in `ActionMenu.tsx`); `npm run build` PASS with a >500 kB chunk warning (posthog-js adds to the bundle).
  - monke-observability: python 51 passed; web 11 passed.
  - Live: frontend dev server loaded PostHog EU config and modules (HTTP 200: config, recorder, exception autocapture, tracing headers). Events from the automated browser were dropped by PostHog's bot filter (ERR-12), so **arrival of events in PostHog is not yet verified**. API could not start without Redis (ERR-11); Docker is not installed, so Postgres/Redis and real analyses could not run.
- **Remaining risks / unverified:** event arrival in PostHog; LLM cost events with real Groq calls; worker jobs are not linked to a user (analyses don't store who started them — passing the user through the job queue would change 4 enqueue sites); Session Replay records page text (inputs masked by default) — review masking before production.
- **Outcome:** PARTIAL — code complete and tested locally; live end-to-end blocked on running Postgres/Redis and a real (non-automated) browser visit.

## [2026-11-23] Task: first push to the public GitHub repo

- **User request:** add remote `https://github.com/MonkE-techh/monke-observability.git`, branch `main`, push.
- **Pre-push review:** no tokens/keys in tracked files; env files git-ignored. Found and reported: the user's email in 4 test files; `HANDOFF.md` names a client and a colleague's personal GitHub account; local paths in logs; commit author is a personal Gmail.
- **User decision:** replace the email in tests only; keep `HANDOFF.md`, logs and author as they are.
- **Changes:** test sample address → `person@example.com` (hash vector `542d240129883c01`) in `python/tests/test_core.py`, `web/src/index.test.ts`, `admin/backend/tests/test_auth.py`, `admin/backend/tests/test_settings.py`; folded into the unpushed first commit (`git commit --amend --no-edit`, approved: commit had never been pushed).
- **Checks:** python 51 passed; web 11 passed; admin backend 89 passed.
