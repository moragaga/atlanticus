from pathlib import Path

from atlanticus.configuration import ConfigurationBootstrap
from atlanticus.operational_data.processes.meteodata.composition import build_composition
from atlanticus.operational_data.processes.meteodata.settings import configuration_specs


def test_composition_uses_existing_http_dataset_and_runtime(tmp_path: Path):
    environ = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'operational-data-meteodata-local',
        'VOLUMEN_PATH': str(tmp_path),
        'METEODATA_BASE_URL': 'https://pelambres.meteodata.cl/met/',
        'METEODATA_TOKEN': 'local-fake-token',
        'METEODATA_PROJECTION_TIMESTAMP_MODE': 'epoch_utc',
    }
    config = ConfigurationBootstrap.from_process(
        specs=configuration_specs(), process_values=environ,
    ).load(process_values=environ)
    composition = build_composition(configuration=config)
    assert composition.definition.job_key == 'meteodata-materialization'
    assert composition.definition.run_once is True
    assert composition.definition.sleep_seconds == 0
    assert composition.definition.iteration_timeout_seconds < composition.definition.execution_timeout_seconds
    assert composition.settings.http.token == 'local-fake-token'
    assert composition.runtime_configuration.application == 'operational-data-meteodata-local'
    assert composition.job.materializer.runtime is composition.dataset_runtime
