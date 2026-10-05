from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.data_producers.fabrica import FabricaValueKind
from atlanticus.kernel import Environment
from atlanticus.operational_data.processes.fabrica_kpis.catalog import DATASETS, build_catalog
from atlanticus.operational_data.processes.fabrica_kpis.composition import (
    JOB_DEFINITION,
    build_composition,
)
from atlanticus.operational_data.processes.fabrica_kpis.settings import configuration_specs


def test_empty_catalog_is_independent_and_declarative() -> None:
    catalog = build_catalog()
    assert catalog.stream_key == 'kpis'
    assert [(dataset.name, dataset.source_value) for dataset in DATASETS] == [
        ('daily', 'DAY'),
        ('weekly', '7LD'),
    ]
    assert DATASETS[0].partition_dimensions == ('year', 'month')
    assert DATASETS[1].partition_dimensions == ()
    assert all(dataset.metrics == () for dataset in DATASETS)
    assert FabricaValueKind.FLOAT.value == 'float'
    assert JOB_DEFINITION.service_name == 'fabrica-kpis'
    assert JOB_DEFINITION.run_once is True


def test_settings_require_only_own_storage_and_empty_catalog_skips_storage(tmp_path) -> None:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'operational-data-fabrica-kpis-local',
        'VOLUMEN_PATH': str(tmp_path),
        'STORAGE_ACCOUNT_SAS_URL_FABRICA_KPIS': 'https://a.blob.core.windows.net/kpis?sv=1',
        'FABRICA_IDLE_SECONDS': '5',
    }
    configuration = ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )
    assert not any('FABRICA_PLANES' in spec.key for spec in configuration_specs())
    composition = build_composition(configuration=configuration)
    assert composition.producer.storages == {}
    assert composition.producer.materializers == ()
