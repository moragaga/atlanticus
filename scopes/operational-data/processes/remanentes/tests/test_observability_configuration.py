from atlanticus.configuration import ConfigurationBootstrap
from atlanticus.operational_data.processes.remanentes.settings import configuration_specs


def test_file_logs_flag_survives_local_configuration_bootstrap(tmp_path) -> None:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'operational-data-remanentes',
        'VOLUMEN_PATH': str(tmp_path),
        'STORAGE_ACCOUNT_CONNECTION_STRING_REMANENTES': 'UseDevelopmentStorage=true',
        'STORAGE_ACCOUNT_CONTAINER_NAME_REMANENTES': 'dataproduct',
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'false',
    }
    bootstrap = ConfigurationBootstrap.from_process(
        specs=configuration_specs(),
        process_values=values,
        configuration_root=tmp_path,
    )

    configuration = bootstrap.load(process_values=values)

    assert configuration.require('ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED') == 'false'
