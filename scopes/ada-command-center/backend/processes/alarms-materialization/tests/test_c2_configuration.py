from pathlib import Path

from ada_command_center.domain.alarms import ALARM_CONFIGURATION_SOURCE_KEY
from ada_command_center.processes.alarms_materialization.settings import (
    AlarmMaterializationSettings,
    configuration_specs,
)
from ada_command_center.web.alarms.projection.cosmos import (
    ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE,
)
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def test_materialization_uses_fixed_source_and_projection_with_manual_connections(tmp_path: Path):
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-command-center',
        'VOLUMEN_PATH': str(tmp_path),
        'ALARM_COSMOS_ENDPOINT': 'http://localhost:8081',
        'ALARM_COSMOS_KEY': 'test-only-key',
        'ALARM_COSMOS_DATABASE_NAME': 'manual-db',
        'ALARM_QUALIFICATIONS_FILE': str(tmp_path / 'qualification.json'),
        'ALARM_MATERIALIZATION_POLL_SECONDS': '30',
    }
    resolved = ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )
    settings = AlarmMaterializationSettings.from_configuration(resolved)
    assert settings.source_key == ALARM_CONFIGURATION_SOURCE_KEY
    assert settings.projection_container == ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE.default_physical_name
    assert settings.cosmos.database_name == 'manual-db'
    assert settings.volume_path == tmp_path
    spec_names = {spec.key for spec in configuration_specs()}
    assert 'ALARM_CONFIGURATION_SOURCE_KEY' not in spec_names
    assert 'ALARM_PROJECTION_CONTAINER' not in spec_names
