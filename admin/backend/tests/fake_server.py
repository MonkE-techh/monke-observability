"""Local preview with made-up data (no PostHog, sign-in off). Test tooling only — never deployed.

uv run python tests/fake_server.py      # then open http://127.0.0.1:8000
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import uvicorn

from monke_admin.main import create_app
from monke_admin.posthog import QueryError
from monke_admin.settings import Settings

APPS = ["engagement-bot-checker", "keyword-radar", "creator-curation", "campaign-dashboard", "old-prototype"]
REPO = Path(__file__).resolve().parents[3]


class FakeClient:
    def __init__(self) -> None:
        self.rng = random.Random(7)

    async def run(self, sql: str, *, name: str):
        r = self.rng
        now = datetime.now(UTC)
        if name == "tiles":
            return [
                {
                    "requests": 48210.0,
                    "errors_5xx": 212,
                    "avg_ms": 284.2,
                    "slowest_ms": 14250.0,
                    "visitors": 391,
                    "llm_calls": 1840,
                    "llm_cost_usd": 4.3712,
                }
            ]
        if name == "apps":
            rows = [
                ("engagement-bot-checker", 18240, 120, 410.0, 14250.0, 160, 4.1, now - timedelta(minutes=3)),
                ("keyword-radar", 9120, 12, 190.0, 5200.0, 74, 0.27, now - timedelta(hours=1)),
                ("creator-curation", 20850, 80, 150.0, 3900.0, 157, 0.0, now - timedelta(minutes=12)),
                ("old-prototype", 12, 0, 80.0, 120.0, 0, 0.0, now - timedelta(days=3)),
            ]
            return [
                {
                    "app": a,
                    "requests": q,
                    "errors_5xx": e,
                    "avg_ms": m,
                    "slowest_ms": s,
                    "visitors": v,
                    "llm_cost_usd": c,
                    "last_event": t.isoformat(),
                }
                for a, q, e, m, s, v, c, t in rows
            ]
        if name == "daily":
            start = date.today() - timedelta(days=29)
            return [
                {"day": (start + timedelta(days=d)).isoformat(), "app": a, "requests": r.randint(100, 900)}
                for d in range(30)
                for a in APPS[:3]
            ]
        if name == "heatmap":
            return [
                {
                    "weekday": d,
                    "hour": h,
                    "requests": max(0, int((40 if 10 <= h <= 19 else 5) * (0.6 if d > 5 else 1) * r.uniform(0.5, 1.5))),
                }
                for d in range(1, 8)
                for h in range(24)
            ]
        if name == "routes":
            return [
                {"route": p, "requests": q, "errors_5xx": e, "avg_ms": m, "slowest_ms": s}
                for p, q, e, m, s in [
                    ("/api/analyses", 6200, 40, 520.0, 14250.0),
                    ("/api/analyses/{analysis_id}", 5100, 3, 120.0, 900.0),
                    ("/api/creators/{creator_id}/refresh", 2400, 70, 2100.0, 12000.0),
                    ("/api/auth/me", 4540, 0, 18.0, 210.0),
                ]
            ]
        if name == "errors":
            return [
                {
                    "timestamp": (now - timedelta(minutes=17 * i)).isoformat(),
                    "method": "POST",
                    "route": "/api/creators/{creator_id}/refresh",
                    "status_code": 502 if i % 3 else 500,
                    "error_type": "ReadTimeout" if i % 2 else None,
                    "user_id": f"engagement-bot-checker:{i + 3}",
                }
                for i in range(6)
            ]
        if name == "llm_models":
            return [
                {
                    "model": "llama-3.3-70b-versatile",
                    "calls": 640,
                    "input_tokens": 1_820_000,
                    "output_tokens": 210_000,
                    "cost_usd": 3.64,
                    "errors": 4,
                },
                {
                    "model": "llama-3.1-8b-instant",
                    "calls": 1200,
                    "input_tokens": 2_400_000,
                    "output_tokens": 300_000,
                    "cost_usd": 0.144,
                    "errors": 0,
                },
            ]
        if name == "llm_sources":
            return [
                {"source": "analysis", "calls": 1700, "cost_usd": 3.9},
                {"source": "explain", "calls": 140, "cost_usd": 0.2},
            ]
        if name == "llm_users":
            return [
                {"user_id": f"engagement-bot-checker:{i}", "calls": 300 - 40 * i, "cost_usd": 1.2 - 0.15 * i}
                for i in range(1, 6)
            ]
        if name == "visitors_country":
            return [{"value": "India", "visitors": 140}, {"value": "United States", "visitors": 12}]
        if name == "visitors_device":
            return [{"value": "Desktop", "visitors": 120}, {"value": "Mobile", "visitors": 40}]
        if name == "visitors_browser":
            raise QueryError("posthog_timeout")  # shows a panel error state in the preview
        return []


if __name__ == "__main__":
    settings = Settings(
        posthog_api_key="fake",
        posthog_project_id="0",
        auth_disabled=True,
        app_env="development",
        apps_file=REPO / "apps.yaml",
    )
    uvicorn.run(create_app(settings, client=FakeClient()), host="127.0.0.1", port=8000)
