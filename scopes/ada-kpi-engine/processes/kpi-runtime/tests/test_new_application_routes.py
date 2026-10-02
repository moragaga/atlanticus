from ada.processes.kpi_runtime.settings import KpiRuntimeSettings, configuration_specs
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def test_kpi_runtime_settings_accept_all_operational_producer_applications() -> None:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'ada-kpi-runtime-local',
        'VOLUMEN_PATH': '/tmp/atlanticus',
        'PI_SOURCE': 'NOTPII',
        'PI_APPLICATION': 'operational-data-notpii-local',
        'FABRICA_PLANES_APPLICATION': 'operational-data-fabrica-planes-local',
        'FABRICA_KPIS_APPLICATION': 'operational-data-fabrica-kpis-local',
        'METEODATA_APPLICATION': 'operational-data-meteodata-local',
        'KPI_POLL_INTERVAL_SECONDS': '1',
        'REPROCESS_CURRENT': 'false',
    }
    config = ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )
    settings = KpiRuntimeSettings.from_configuration(config)
    assert settings.pi_application == 'operational-data-notpii-local'
    assert settings.fabrica_planes_application == 'operational-data-fabrica-planes-local'
    assert settings.fabrica_kpis_application == 'operational-data-fabrica-kpis-local'
    assert settings.meteodata_application == 'operational-data-meteodata-local'
    assert 'METEODATA_APPLICATION' in {spec.key for spec in configuration_specs()}
