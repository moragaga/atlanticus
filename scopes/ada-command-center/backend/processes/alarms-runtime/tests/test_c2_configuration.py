from pathlib import Path

from ada_command_center.domain.alarms import ALARM_CONFIGURATION_SOURCE_KEY
from ada_command_center.processes.alarms_runtime.settings import (
    AlarmRuntimeSettings,
    configuration_specs,
)
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def test_runtime_derives_source_without_own_config_and_keeps_producer_routing(tmp_path: Path):
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-command-center',
        'VOLUMEN_PATH': str(tmp_path),
        'PI_SOURCE': 'NOTPII',
        'PI_APPLICATION': 'developer-notpii',
        'ALARM_TECHNICAL_EVIDENCE_CONTRACT_KEY': 'approved.technical',
        'ALARM_TECHNICAL_EVIDENCE_CONTRACT_VERSION': 'v1',
        'ALARM_RUNTIME_POLL_SECONDS': '5',
    }
    resolved = ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )
    settings = AlarmRuntimeSettings.from_configuration(resolved)
    assert settings.source_key == ALARM_CONFIGURATION_SOURCE_KEY
    assert settings.pi_application == 'developer-notpii'
    assert 'ALARM_CONFIGURATION_SOURCE_KEY' not in {spec.key for spec in configuration_specs()}
