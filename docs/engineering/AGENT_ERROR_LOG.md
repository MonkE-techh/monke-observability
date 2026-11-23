# Agent error log

## [2026-11-23] ERR-1: test expected kebab-case error for an empty app name

- **Context:** `python/tests/test_core.py::test_init_rejects_app_names_that_are_not_kebab_case[]`, `uv run pytest`.
- **Expected:** `ValueError` mentioning kebab-case.
- **Observed:** `ValueError: APP_NAME is not set…` — an empty name is treated as "not set".
- **Classification:** INTRODUCED (mistake in the new test, not in the code).
- **Root cause:** the empty-string case belongs to `test_init_requires_app_name`, which already covers it.
- **Resolution:** replaced `""` with `"Radar"` (uppercase) in the parametrised cases.
- **Verification:** `uv run pytest -q` — 13 passed at that point.
- **Status:** RESOLVED

## [2026-11-23] ERR-2: Starlette TestClient deprecation warning; dependency swap denied

- **Context:** `uv run pytest` warns `Using httpx with starlette.testclient is deprecated; install httpx2 instead`.
- **Expected:** clean test output.
- **Observed:** the warning; the attempt to run `uv remove --dev httpx && uv add --dev httpx2` was denied by the session's permission check.
- **Classification:** ENVIRONMENT (tooling permission); warning is from dev dependencies only.
- **Root cause:** Starlette 1.10 prefers `httpx2` for its test client.
- **Resolution:** left as is; swap the dev dependency to `httpx2>=2.16` when allowed (Keyword Radar already uses it).
- **Verification:** none yet; tests pass with the warning.
- **Status:** OPEN

## [2026-11-23] ERR-3: OTel logs test read private attributes; SDK LoggingHandler deprecated

- **Context:** `python/tests/test_logs.py`, `uv run pytest`.
- **Expected:** test checks the exporter endpoint and auth header.
- **Observed:** `AttributeError: 'OTLPLogExporter' object has no attribute '_headers'`; plus `DeprecationWarning: LoggingHandler in opentelemetry-sdk is deprecated`.
- **Classification:** INTRODUCED (fragile test) + EXTERNAL (upstream deprecation in opentelemetry-sdk 1.45).
- **Root cause:** the test inspected SDK internals; the replacement handler lives in the beta `opentelemetry-instrumentation-logging` package.
- **Resolution:** added public `exporter_settings()` and tested it instead of internals; kept the SDK handler and filtered only that one deprecation message at construction, with a TODO to migrate once the replacement is stable. A test asserts setup emits no warnings.
- **Verification:** `uv run pytest -q` — 40 passed.
- **Status:** MITIGATED (migration to the new handler still to do)

## [2026-11-23] ERR-4: Chrome not installed for the DevTools browser tool

- **Context:** browser check of the admin page via chrome-devtools MCP `new_page`.
- **Expected:** a controllable Chrome tab.
- **Observed:** `Could not find Google Chrome executable for channel 'stable'`.
- **Classification:** ENVIRONMENT
- **Root cause:** Chrome is not installed; Edge is.
- **Resolution:** used the installed `agent-browser` CLI instead.
- **Verification:** screenshots taken at 1280 px and 390 px, light and dark.
- **Status:** RESOLVED (workaround)

## [2026-11-23] ERR-5: daily chart blank in a full-page screenshot of the app page

- **Context:** `agent-browser screenshot --full` on `/apps/engagement-bot-checker?range=45`.
- **Expected:** stacked bars.
- **Observed:** empty chart area in that capture only.
- **Classification:** ENVIRONMENT (capture artefact)
- **Root cause:** API returned the data; the DOM held 90 bars at normal viewport; a viewport screenshot rendered the chart. The full-page capture resizes the viewport and caught Recharts mid re-measure.
- **Resolution:** none needed in the app.
- **Verification:** viewport screenshot shows the chart; DOM bar count 90 on both pages.
- **Status:** RESOLVED (not an app bug)

## [2026-11-23] ERR-6: vite.config.ts `test` block failed type-check

- **Context:** `npx tsc --noEmit` in admin/frontend.
- **Observed:** `TS2769 … 'test' does not exist in type 'UserConfigExport'`.
- **Classification:** INTRODUCED
- **Root cause:** `defineConfig` imported from `vite` instead of `vitest/config`.
- **Resolution:** import from `vitest/config`.
- **Verification:** `tsc --noEmit` and `npm run build` pass.
- **Status:** RESOLVED

## [2026-11-23] ERR-7: non-numeric `exp` claim would crash sign-in with HTTP 500

- **Context:** `admin/backend/src/monke_admin/auth.py` claim checks; new test case `{"exp": "soon"}`.
- **Expected:** sign-in refused (`/?auth=denied`).
- **Observed:** `ValueError: could not convert string to float: 'soon'`.
- **Classification:** INTRODUCED (caught by test before use)
- **Resolution:** `exp` must be a number and in the future.
- **Verification:** `uv run pytest` — RED then GREEN; suite 66 passed at that point.
- **Status:** RESOLVED

## [2026-11-23] ERR-8: Docker not installed; image build not verified

- **Context:** `admin/Dockerfile`.
- **Observed:** `docker: command not found`.
- **Classification:** ENVIRONMENT
- **Resolution:** Render will build the image; first deploy is the first real build.
- **Verification:** NOT RUN.
- **Status:** OPEN

## [2026-11-23] ERR-9: route template lost the include_router prefix on FastAPI 0.162+

- **Context:** pilot test `test_signed_in_request_is_recorded_with_a_hashed_user_id_and_no_email`.
- **Expected:** `route == "/api/auth/me"`.
- **Observed:** `"/auth/me"`. Probe showed FastAPI 0.162/0.165 wraps included routers in a lazy `_IncludedRouter`; `scope["route"].path` is relative to it.
- **Classification:** INTRODUCED (package assumed older FastAPI behaviour; its own tests did not use prefixed routers)
- **Root cause:** confirmed by probe script (scope keys and route path printed).
- **Resolution:** `context.route_template` rebuilds the prefix from `scope["path"]` and `path_params`; falls back to the route's own template when the prefix would contain a param value.
- **Verification:** new package tests (prefixed router; id in prefix) RED→GREEN; package 51 passed; pilot test passes.
- **Status:** RESOLVED

## [2026-11-23] ERR-10: `Analysis.created_by_email` does not exist

- **Context:** pilot `app/pipeline/runner.py` attribution line; `uv run mypy`.
- **Observed:** `"Analysis" has no attribute "created_by_email"` (only `PricingRun` has it).
- **Classification:** INTRODUCED (caught by type check; the runner path needs a database, so tests skipped it)
- **Resolution:** removed the attribution line and the unused helper; analysis jobs are attributed to job + analysis id only.
- **Verification:** mypy clean on changed files; backend 313 passed.
- **Status:** RESOLVED

## [2026-11-23] ERR-11: pilot API cannot start without Redis

- **Context:** `uv run uvicorn app.main:app` in the worktree, no Redis running.
- **Observed:** `redis.exceptions.TimeoutError: Timeout connecting to server` → `Application startup failed`.
- **Classification:** PRE-EXISTING / ENVIRONMENT (lifespan catches `OSError` only; redis' TimeoutError is not one). Not changed by the pilot.
- **Resolution:** none in this task (outside scope); Redis/Postgres need Docker (`docker compose up -d postgres redis`), which is not installed here.
- **Verification:** BLOCKED.
- **Status:** OPEN

## [2026-11-23] ERR-12: PostHog drops events from the automated browser

- **Context:** agent-browser on the pilot frontend (`http://localhost:5173`).
- **Observed:** console `Events are being dropped because the user agent looks like a bot`.
- **Classification:** ENVIRONMENT (PostHog's bot filter, by design)
- **Resolution:** none in the app (the filter should stay on). Verify with a real browser visit.
- **Verification:** config and modules loaded with HTTP 200; event arrival not verified.
- **Status:** OPEN
