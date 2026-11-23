# Monk-E admin page

Internal page for the tech team: requests, server errors, response times, visitors, peak hours and LLM cost for every Monk-E app, read live from PostHog. Design: `docs/superpowers/specs/2026-11-23-admin-page-design.md`.

- `backend/` — FastAPI. Holds the PostHog personal API key (query:read), runs fixed HogQL queries (at most 3 at once, cached 5 minutes), Google sign-in with an email allow-list, serves the built page.
- `frontend/` — React + Vite + Recharts. Builds into `backend/static/`.
- Apps listed come from `apps.yaml` at the repo root, plus any app seen in the data (flagged "not in apps.yaml").

## Run locally

```
cd admin/frontend && npm install && npm run build
cd ../backend && uv sync
uv run --env-file .env uvicorn monke_admin.main:create_app --factory --port 8000   # see ../.env.example
```

Preview with made-up data, no PostHog and no sign-in: `uv run python tests/fake_server.py`, then open <http://127.0.0.1:8000>. For frontend work, `npm run dev` in `frontend/` proxies `/api` to port 8000.

## Checks

```
cd admin/backend && uv run pytest && uv run ruff check .
cd admin/frontend && npm test && npm run build
```

## Deploy

`render.yaml` at the repo root describes one Docker web service (`admin/Dockerfile`, build context = repo root). Setup steps and links: `docs/SETUP_LINKS.md`. On the free plan, an UptimeRobot check on `/api/health` every 5 minutes keeps it from sleeping (mind the 750 free hours a month per workspace).

## Limits

- LLM figures cover at most the last 30 days (PostHog keeps LLM events 30 days) until the nightly rollup exists.
- "Slowest" is the single slowest request; no percentiles yet.
- PostHog's query API allows 2400 queries an hour per project; one page load runs 4 (overview) or 11 (app page) queries, cached 5 minutes.
