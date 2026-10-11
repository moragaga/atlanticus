from __future__ import annotations

from types import SimpleNamespace

import pytest

from ada.web.application.generic import host
from ada.web.application.generic.settings import AdaGenericSettings


def test_generic_settings_inherit_web_port_contract() -> None:
    settings = AdaGenericSettings.from_mapping({'ADA_TOOL_NAMESPACE': 'test-tool'})
    override = AdaGenericSettings.from_mapping(
        {'ADA_TOOL_NAMESPACE': 'test-tool', 'ATLANTICUS_WEB_PORT': '8052'}
    )

    assert settings.web_port == 8000
    assert override.web_port == 8052


@pytest.mark.parametrize('port', (8000, 8051))
def test_operational_entrypoint_uses_same_settings_for_worker_and_flask(
    monkeypatch, port: int
) -> None:
    settings = SimpleNamespace(web_port=port)
    worker = SimpleNamespace(application=object(), close=lambda: None)
    captured = {}
    resolutions = []

    def read_settings():
        resolutions.append('read')
        return settings

    def create_worker_runtime(**kwargs):
        captured['worker_settings'] = kwargs['settings']
        return worker

    def run_web_application(application, *, port):
        captured['application'] = application
        captured['port'] = port

    monkeypatch.setattr(host, 'AdaGenericSettings', read_settings)
    monkeypatch.setattr(host, 'create_worker_runtime', create_worker_runtime)
    monkeypatch.setattr(host, 'run_web_application', run_web_application)

    host.run_operational_application()

    assert resolutions == ['read']
    assert captured == {
        'worker_settings': settings,
        'application': worker.application,
        'port': port,
    }
