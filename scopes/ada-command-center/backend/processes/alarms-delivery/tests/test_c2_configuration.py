from ada_command_center.domain.alarms import ALARM_CONFIGURATION_SOURCE_KEY
from ada_command_center.processes.alarms_delivery.settings import (
    AlarmDeliverySettings,
    configuration_specs,
)
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def test_delivery_derives_source_and_retains_independent_polling():
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-command-center',
        'VOLUMEN_PATH': '/operator/selected/volume',
        'ALARM_DELIVERY_POLL_SECONDS': '7',
        'ALARM_DELIVERY_MAX_FACTS_PER_ITERATION': '150',
        'ALARM_DELIVERY_MAX_WORKERS': '3',
    }
    resolved = ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )
    settings = AlarmDeliverySettings.from_configuration(resolved)
    assert settings.source_key == ALARM_CONFIGURATION_SOURCE_KEY
    assert (settings.poll_seconds, settings.max_facts_per_iteration, settings.max_workers) == (7, 150, 3)
    assert 'ALARM_CONFIGURATION_SOURCE_KEY' not in {spec.key for spec in configuration_specs()}
