import pytest

from ada.processes.kpi_materialization.errors import KpiMaterializationSettingsError
from ada.processes.kpi_materialization.settings import (
    KpiMaterializationSettings,
    configuration_specs,
)
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def _configuration(interval='30'):
    values = {
        'ENVIRONMENT': 'local',
        'POLL_INTERVAL_SECONDS': interval,
    }
    return ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )


def test_settings_resolve_generic_poll_interval():
    assert (
        KpiMaterializationSettings.from_configuration(_configuration('2.5')).poll_interval_seconds
        == 2.5
    )


def test_settings_reject_non_positive_poll_interval():
    with pytest.raises(KpiMaterializationSettingsError, match='positive'):
        KpiMaterializationSettings.from_configuration(_configuration('0'))


def test_configuration_specs_leave_cosmos_variables_dynamic():
    keys = {item.key for item in configuration_specs()}
    assert 'POLL_INTERVAL_SECONDS' in keys
    assert all('COSMOS' not in key for key in keys)
