from atlanticus.configuration import ConfigurationBootstrap
from atlanticus.integrations.pi.contracts import PiExtractionMode
from atlanticus.operational_data.processes.notpii.settings import configuration_specs


def test_file_logs_flag_survives_local_configuration_bootstrap(tmp_path) -> None:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'operational-data-notpii',
        'VOLUMEN_PATH': str(tmp_path),
        'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'false',
    }
    bootstrap = ConfigurationBootstrap.from_process(
        specs=configuration_specs(active_modes=(PiExtractionMode.INTERPOLATED,)),
        process_values=values,
        configuration_root=tmp_path,
    )

    configuration = bootstrap.load(process_values=values)

    assert configuration.require('ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED') == 'false'
