from __future__ import annotations

import pytest

from monke_observability import Observability, init, namespaced_user_id


def test_capture_tags_every_event_with_app_and_environment(fake):
    obs = Observability(app_name="radar", environment="production", client=fake)

    obs.capture("thing_happened", distinct_id="radar:1", properties={"x": 1})

    assert fake.events == [
        {
            "event": "thing_happened",
            "distinct_id": "radar:1",
            "properties": {"x": 1, "app_name": "radar", "environment": "production"},
        }
    ]


def test_capture_without_user_is_personless(fake):
    obs = Observability(app_name="radar", environment="production", client=fake)

    obs.capture("thing_happened", distinct_id=None, properties={})

    sent = fake.events[0]
    assert sent["distinct_id"] is None
    assert sent["properties"]["$process_person_profile"] is False


def test_init_reads_settings_from_environment(monkeypatch, fake):
    monkeypatch.setenv("APP_NAME", "creator-curation")
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("MONKE_SAMPLE_RATE", "0.25")

    obs = init(client=fake)

    assert (obs.app_name, obs.environment, obs.sample_rate) == ("creator-curation", "staging", 0.25)
    assert obs.enabled


def test_init_without_token_is_disabled_and_sends_nothing(monkeypatch):
    monkeypatch.setenv("APP_NAME", "radar")

    obs = init()
    obs.capture("thing_happened", distinct_id=None, properties={})

    assert not obs.enabled


def test_init_requires_app_name():
    with pytest.raises(ValueError, match="APP_NAME"):
        init(token="phc_test")


@pytest.mark.parametrize("bad", ["Radar App", "radar_app", "Radar", "-radar"])
def test_init_rejects_app_names_that_are_not_kebab_case(bad):
    with pytest.raises(ValueError, match="kebab-case"):
        init(app_name=bad, token="phc_test")


@pytest.mark.parametrize("rate", ["0", "1.5", "abc"])
def test_init_rejects_invalid_sample_rate(monkeypatch, rate):
    monkeypatch.setenv("MONKE_SAMPLE_RATE", rate)
    with pytest.raises(ValueError, match="sample rate"):
        init(app_name="radar", token="phc_test")


def test_namespaced_user_id_prefixes_app_name():
    assert namespaced_user_id("radar", 42) == "radar:42"
    assert namespaced_user_id("radar", "radar:42") == "radar:42"
    assert namespaced_user_id("radar", None) is None
    assert namespaced_user_id("radar", "") is None


def test_pseudonymous_id_is_a_short_stable_hash_of_the_normalised_value():
    from monke_observability import pseudonymous_id

    # sha256("person@example.com")[:16]; the browser package must produce the same value.
    assert pseudonymous_id("person@example.com") == "542d240129883c01"
    assert pseudonymous_id("  Person@Example.com ") == "542d240129883c01"
    assert pseudonymous_id("") is None
    assert pseudonymous_id(None) is None
