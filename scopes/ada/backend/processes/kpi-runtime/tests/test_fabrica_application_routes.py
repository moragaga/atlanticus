from ada.processes.kpi_runtime.settings import KpiRuntimeSettings, configuration_specs
from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.kernel import Environment


def test_kpi_runtime_configures_fabrica_sources_independently() -> None:
    values = {
        'ENVIRONMENT': 'local', 'APPLICATION': 'ada-kpi-runtime', 'VOLUMEN_PATH': '/tmp/atlanticus',
        'PI_SOURCE': 'NOTPII', 'PI_APPLICATION': 'operational-data-notpii',
        'FABRICA_PLANES_APPLICATION': 'operational-data-fabrica-planes',
        'KPI_POLL_INTERVAL_SECONDS': '1', 'REPROCESS_CURRENT': 'false',
    }
    configuration = ResolvedConfiguration(
        environment=Environment.from_value('local'), values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )
    settings = KpiRuntimeSettings.from_configuration(configuration)
    assert settings.fabrica_planes_application == 'operational-data-fabrica-planes'
    assert settings.fabrica_kpis_application is None
    keys = {spec.key for spec in configuration_specs()}
    assert 'FABRICA_PLANES_APPLICATION' in keys
    assert 'FABRICA_KPIS_APPLICATION' in keys
    assert 'FABRICA_APPLICATION' not in keys
