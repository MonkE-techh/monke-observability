from __future__ import annotations

import logging
import warnings

import pytest

from monke_observability import Observability
from monke_observability.logs import exporter_settings, setup_otel_logs


@pytest.fixture
def root_handlers():
    before = list(logging.getLogger().handlers)
    yield
    for handler in logging.getLogger().handlers:
        if handler not in before:
            logging.getLogger().removeHandler(handler)


def test_without_token_no_handler_is_added(fake, root_handlers):
    obs = Observability(app_name="radar", environment="production", client=fake)
    before = list(logging.getLogger().handlers)

    assert setup_otel_logs(obs, token=None) is None
    assert logging.getLogger().handlers == before


def test_exporter_targets_posthog_logs_endpoint_with_project_token():
    endpoint, headers = exporter_settings(token="phc_test", host="https://eu.i.posthog.com/")

    assert endpoint == "https://eu.i.posthog.com/i/v1/logs"
    assert headers == {"Authorization": "Bearer phc_test"}


def test_logs_are_tagged_with_app_as_service_name_and_root_logger_exports_them(fake, root_handlers):
    obs = Observability(app_name="radar", environment="staging", client=fake)
    before = len(logging.getLogger().handlers)

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # setup itself must not emit warnings into every app's start-up
        provider = setup_otel_logs(obs, token="phc_test", host="https://eu.i.posthog.com")

    assert provider is not None
    attrs = provider.resource.attributes
    assert attrs["service.name"] == "radar"
    assert attrs["deployment.environment"] == "staging"
    assert len(logging.getLogger().handlers) == before + 1
    provider.shutdown()
