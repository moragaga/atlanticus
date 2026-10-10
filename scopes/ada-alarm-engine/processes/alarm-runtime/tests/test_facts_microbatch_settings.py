from __future__ import annotations

import pytest

from ada.processes.alarm_runtime import settings as alarm_settings


class _Configuration:
    def __init__(self, values):
        self.values = values

    def require(self, key):
        return self.values[key]

    def get(self, key):
        return self.values.get(key)


def _settings(monkeypatch, **overrides):
    monkeypatch.setattr(alarm_settings, 'ResolvedConfiguration', _Configuration)
    values = {
        'PI_SOURCE': 'NOTPII',
        'PI_APPLICATION': 'pi-data',
        'ALARM_RUNTIME_POLL_SECONDS': '1',
    }
    values.update(overrides)
    return alarm_settings.AlarmRuntimeSettings.from_configuration(_Configuration(values))


def test_facts_publication_interval_defaults_independently_of_poll(monkeypatch):
    resolved = _settings(monkeypatch)
    assert resolved.poll_interval_seconds == 1.0
    assert resolved.facts_publish_interval_seconds == 10.0
    assert any(
        item.key == 'ALARM_RUNTIME_FACTS_PUBLISH_SECONDS' and item.default == '10'
        for item in alarm_settings.configuration_specs()
    )


def test_facts_publication_interval_can_be_configured(monkeypatch):
    resolved = _settings(monkeypatch, ALARM_RUNTIME_FACTS_PUBLISH_SECONDS='2.5')
    assert resolved.facts_publish_interval_seconds == 2.5


@pytest.mark.parametrize('value', ['0', '-1', 'nan', 'inf', 'invalid'])
def test_facts_publication_interval_rejects_invalid_values(monkeypatch, value):
    with pytest.raises(Exception, match='positive number'):
        _settings(monkeypatch, ALARM_RUNTIME_FACTS_PUBLISH_SECONDS=value)
