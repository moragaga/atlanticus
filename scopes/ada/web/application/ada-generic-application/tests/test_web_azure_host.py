from __future__ import annotations

from types import SimpleNamespace

import pytest

from ada.web.application.generic import host
from ada.web.application.generic.settings import AdaGenericSettings
from atlanticus.web.configuration import WebEnvironment


class _Sink:
    def __init__(self) -> None:
        self.close_count = 0

    def emit(self, event) -> None:
        pass

    def close(self) -> None:
        self.close_count += 1


def _settings() -> AdaGenericSettings:
    return AdaGenericSettings.from_mapping({
        'ADA_TOOL_NAMESPACE': 'example',
        'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'export',
        'ATLANTICUS_AZURE_OBSERVABILITY_PROFILE': 'slim',
        'ATLANTICUS_ENVIRONMENT': 'local',
        'APPLICATION_INSIGHTS_CONNECTION_STRING': 'InstrumentationKey=test',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'false',
    })


def test_worker_injects_owned_sink_before_web_composition(monkeypatch) -> None:
    sink = _Sink()
    seen = {}
    monkeypatch.setattr(host, 'create_web_azure_event_sink',
                        lambda **kwargs: (seen.update(kwargs), sink)[1])
    monkeypatch.setattr(host, 'create_local_configuration_manager_stores', lambda: object())
    monkeypatch.setattr(host, '_local_identity', lambda: object())
    monkeypatch.setattr(host, 'create_operational_application_runtime',
                        lambda **kwargs: (seen.update({'injected': kwargs['web_event_sink']}),
                                          SimpleNamespace(dash=object(), server=object()))[1])
    monkeypatch.setattr(host, 'prepare_dash_worker', lambda dash: None)
    worker = host.create_worker_runtime(settings=_settings())
    assert seen['injected'] is sink
    assert seen['application'] == 'ada-generic-application'
    assert seen['mode'] == 'export'
    assert seen['environment'] is WebEnvironment.LOCAL
    worker.close()
    worker.close()
    assert sink.close_count == 1


def test_worker_closes_sink_when_composition_fails(monkeypatch) -> None:
    sink = _Sink()
    monkeypatch.setattr(host, 'create_web_azure_event_sink', lambda **kwargs: sink)
    monkeypatch.setattr(host, 'create_local_configuration_manager_stores', lambda: object())
    monkeypatch.setattr(host, '_local_identity', lambda: object())

    def fail(**kwargs):
        raise RuntimeError('compose failed')

    monkeypatch.setattr(host, 'create_operational_application_runtime', fail)
    with pytest.raises(RuntimeError, match='compose failed'):
        host.create_worker_runtime(settings=_settings())
    assert sink.close_count == 1


def test_settings_default_to_off_without_backend_environment_alias() -> None:
    settings = AdaGenericSettings.from_mapping({'ADA_TOOL_NAMESPACE': 'example'})
    assert settings.azure_observability_mode == 'off'
    assert settings.azure_observability_profile == 'slim'
    assert settings.environment is WebEnvironment.LOCAL
    assert settings.observability_file_logs_enabled is False


def test_web_disallows_file_logs_even_if_explicitly_requested() -> None:
    with pytest.raises(ValueError):
        AdaGenericSettings.from_mapping({
            'ADA_TOOL_NAMESPACE': 'example',
            'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'true',
        })
