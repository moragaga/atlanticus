from __future__ import annotations

from pathlib import Path

import pytest

from ada_command_center.processes.alarms_runtime.settings import (
    AlarmRuntimeSettings,
    AlarmRuntimeSettingsError,
)
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(volume: Path, **changes: str) -> ResolvedConfiguration:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-command-center',
        'VOLUMEN_PATH': str(volume),
        'PI_SOURCE': 'NOTPII',
        'PI_APPLICATION': 'notpii-local',
        'ALARM_TECHNICAL_EVIDENCE_CONTRACT_KEY': 'test.technical',
        'ALARM_TECHNICAL_EVIDENCE_CONTRACT_VERSION': 'v1',
        'ALARM_RUNTIME_POLL_SECONDS': '5',
        **changes,
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_settings_use_current_pi_routing_without_activating_unconfigured_sources(tmp_path: Path):
    settings = AlarmRuntimeSettings.from_configuration(_configuration(tmp_path))
    assert settings.pi_source == 'notpii'
    assert settings.pi_application == 'notpii-local'
    assert settings.dispatch_application is None
    assert settings.technical_evidence_contract.contract_key == 'test.technical'
    assert settings.poll_interval_seconds == 5


@pytest.mark.parametrize('bad', ('0', '-1', 'nan', 'inf', 'invalid'))
def test_invalid_poll_interval_fails_closed(tmp_path: Path, bad: str):
    configuration = _configuration(tmp_path, ALARM_RUNTIME_POLL_SECONDS=bad)
    with pytest.raises(AlarmRuntimeSettingsError, match='positive number'):
        AlarmRuntimeSettings.from_configuration(configuration)


def test_technical_contract_cannot_be_missing_or_blank(tmp_path: Path):
    configuration = _configuration(tmp_path, ALARM_TECHNICAL_EVIDENCE_CONTRACT_KEY=' ')
    with pytest.raises(AlarmRuntimeSettingsError, match='ALARM_TECHNICAL_EVIDENCE_CONTRACT_KEY'):
        AlarmRuntimeSettings.from_configuration(configuration)


def test_unknown_pi_provider_is_not_silently_replaced(tmp_path: Path):
    configuration = _configuration(tmp_path, PI_SOURCE='unregistered')
    with pytest.raises(AlarmRuntimeSettingsError, match='PI_SOURCE'):
        AlarmRuntimeSettings.from_configuration(configuration)


def test_pi_web_api_is_normalized_without_loading_physical_sources(tmp_path: Path):
    settings = AlarmRuntimeSettings.from_configuration(
        _configuration(tmp_path, PI_SOURCE='PI_WEB_API', PI_APPLICATION='pi-local')
    )
    assert settings.pi_source == 'pi_web_api'
    assert settings.pi_application == 'pi-local'
