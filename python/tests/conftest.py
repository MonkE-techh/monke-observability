from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass
class FakePosthog:
    """Stands in for posthog.Posthog: records what would have been sent."""

    events: list[dict[str, Any]] = field(default_factory=list)
    ai_events: list[dict[str, Any]] = field(default_factory=list)
    flushed: int = 0

    def capture(self, event: str, **kwargs: Any) -> str:
        self.events.append({"event": event, **kwargs})
        return "uuid"

    def capture_ai(self, event: str, **kwargs: Any) -> str:
        self.ai_events.append({"event": event, **kwargs})
        return "uuid"

    exceptions: list[dict[str, Any]] = field(default_factory=list)

    def capture_exception(self, exception: BaseException, **kwargs: Any) -> str:
        self.exceptions.append({"exception": exception, **kwargs})
        return "uuid"

    def flush(self, timeout_seconds: float | None = 10) -> None:
        self.flushed += 1


@pytest.fixture
def fake() -> FakePosthog:
    return FakePosthog()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import monke_observability.core as core

    monkeypatch.setattr(core, "_current", None)
    for name in ("APP_NAME", "APP_ENV", "POSTHOG_PROJECT_TOKEN", "POSTHOG_HOST", "MONKE_SAMPLE_RATE"):
        monkeypatch.delenv(name, raising=False)
