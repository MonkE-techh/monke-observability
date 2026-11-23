"""Optional: ship Python `logging` records to PostHog Logs over OpenTelemetry (OTLP/HTTP).

Needs the `otel` extra:  monke-observability[otel]. Request events work without it.

    obs = init()
    setup_otel_logs(obs)   # token/host default to POSTHOG_PROJECT_TOKEN / POSTHOG_HOST

The request middleware logs one structured line per request on `monke_observability.request`;
with this handler attached those attributes arrive in PostHog Logs with service.name = APP_NAME.
"""

from __future__ import annotations

import logging
import os
import warnings
from typing import Any

from monke_observability import core


def exporter_settings(*, token: str, host: str | None = None) -> tuple[str, dict[str, str]]:
    """OTLP endpoint and headers for PostHog Logs. The project token (phc_) is the credential, not a personal key."""
    base = (host or os.environ.get("POSTHOG_HOST") or core.DEFAULT_HOST).rstrip("/")
    return f"{base}/i/v1/logs", {"Authorization": f"Bearer {token}"}


def setup_otel_logs(
    obs: core.Observability,
    *,
    token: str | None = None,
    host: str | None = None,
    level: int = logging.INFO,
) -> Any | None:
    """Attach an OTel handler to the root logger. Returns the LoggerProvider, or None without a token."""
    project_token = token or os.environ.get("POSTHOG_PROJECT_TOKEN")
    if not project_token:
        return None

    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.resources import Resource

    endpoint, headers = exporter_settings(token=project_token, host=host)
    provider = LoggerProvider(
        resource=Resource.create({"service.name": obs.app_name, "deployment.environment": obs.environment})
    )
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, headers=headers)))
    set_logger_provider(provider)
    with warnings.catch_warnings():
        # The SDK handler still works but is deprecated in favour of the beta opentelemetry-instrumentation-logging
        # package; only that one notice is silenced. TODO: move to the replacement once it is stable.
        warnings.filterwarnings(
            "ignore", message="`LoggingHandler` in `opentelemetry-sdk` is deprecated", category=DeprecationWarning
        )
        handler = LoggingHandler(level=level, logger_provider=provider)
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level > level or root.level == logging.NOTSET:
        root.setLevel(level)
    return provider
