from atlanticus.configuration import ConfigurationBootstrap
from atlanticus.operational_data.processes.pi.settings import configuration_specs


def test_file_logs_flag_survives_local_configuration_bootstrap(tmp_path) -> None:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'operational-data-pi',
        'VOLUMEN_PATH': str(tmp_path),
        'PI_WEB_API_BASE_URL': 'https://pi.example.local/piwebapi/',
        'PI_WEB_API_SERVER': 'PISERVER',
        'PI_WEB_API_USERNAME': 'domain\\user',
        'PI_WEB_API_PASSWORD': 'secret',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'false',
    }
    bootstrap = ConfigurationBootstrap.from_process(
        specs=configuration_specs(),
        process_values=values,
        configuration_root=tmp_path,
    )

    configuration = bootstrap.load(process_values=values)

    assert configuration.require('ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED') == 'false'
