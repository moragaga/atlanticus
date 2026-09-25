import ast
from pathlib import Path

from atlanticus.configuration import ConfigurationSource, ResolvedConfiguration
from atlanticus.data_producers.fabrica import FabricaValueKind
from atlanticus.kernel import Environment
from atlanticus.operational_data.processes.fabrica_planes.catalog import DATASETS, build_catalog
from atlanticus.operational_data.processes.fabrica_planes.composition import (
    JOB_DEFINITION,
    build_composition,
)
from atlanticus.operational_data.processes.fabrica_planes.settings import configuration_specs


def test_empty_catalog_is_independent_and_declarative() -> None:
    catalog = build_catalog()
    assert catalog.stream_key == 'planes'
    assert [(dataset.name, dataset.source_value) for dataset in DATASETS] == [
        ('daily', 'DAY'),
        ('weekly', '7LDB'),
    ]
    assert all(dataset.metrics == () for dataset in DATASETS)
    assert FabricaValueKind.FLOAT.value == 'float'
    assert JOB_DEFINITION.service_name == 'fabrica-planes'
    assert JOB_DEFINITION.run_once is True


def test_settings_require_only_own_storage_and_empty_catalog_skips_storage(tmp_path) -> None:
    values = {
        'ENVIRONMENT': 'local',
        'APPLICATION': 'operational-data-fabrica-planes-local',
        'VOLUMEN_PATH': str(tmp_path),
        'STORAGE_ACCOUNT_SAS_URL_FABRICA_PLANES': 'https://a.blob.core.windows.net/planes?sv=1',
        'FABRICA_IDLE_SECONDS': '5',
    }
    configuration = ResolvedConfiguration(
        environment=Environment.from_value('local'),
        values=values,
        sources={key: ConfigurationSource.PROCESS for key in values},
    )
    assert not any('FABRICA_KPIS' in spec.key for spec in configuration_specs())
    composition = build_composition(configuration=configuration)
    assert composition.producer.storages == {}
    assert composition.producer.materializers == ()


def test_commented_source_mirrors_productive_tree() -> None:
    root = Path(__file__).resolve().parents[1]
    source = root / 'src' / 'atlanticus/operational_data/processes/fabrica_planes/'
    mirror = root / 'commented' / 'atlanticus/operational_data/processes/fabrica_planes/'
    source_files = sorted(file.relative_to(source) for file in source.rglob('*.py'))
    assert source_files == sorted(file.relative_to(mirror) for file in mirror.rglob('*.py'))
    for relative in source_files:
        assert ast.dump(
            ast.parse((source / relative).read_text()), include_attributes=False
        ) == ast.dump(ast.parse((mirror / relative).read_text()), include_attributes=False)
