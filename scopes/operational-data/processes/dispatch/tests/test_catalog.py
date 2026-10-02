import ast
from pathlib import Path

import pytest

from atlanticus.data_producers.sql import (
    DataValueKind,
    SqlColumnDefinition,
    SqlLoadStrategy,
    SqlSourceDefinition,
    SqlStorageMode,
)
from atlanticus.operational_data.processes.dispatch.catalog import build_catalog
from atlanticus.operational_data.processes.dispatch.catalog.definitions import DEFINITIONS
from atlanticus.operational_data.processes.dispatch.catalog.examples import EXAMPLE_DEFINITIONS
from atlanticus.operational_data.processes.dispatch.errors import DispatchCatalogError


def test_catalog_starts_empty_and_requires_configuration() -> None:
    assert DEFINITIONS == ()
    with pytest.raises(DispatchCatalogError, match='at least one source'):
        build_catalog()


def test_examples_preserve_real_dispatch_sources_in_stable_order() -> None:
    assert tuple(item.source_key for item in EXAMPLE_DEFINITIONS) == (
        'tiempos_mlp',
        'shift_info',
        'std_shift_state',
        'std_shift_loads',
        'std_shift_loads_2',
        'std_shift_dumps',
        'std_shift_dumps_nodica',
        'std_shift_loads_2_nodica',
        'std_shift_grade',
        'std_truck',
    )


def test_examples_preserve_partition_and_latest_contracts() -> None:
    shift_sources = tuple(
        item for item in EXAMPLE_DEFINITIONS if item.storage_mode is SqlStorageMode.PARTITIONED
    )
    latest = next(item for item in EXAMPLE_DEFINITIONS if item.source_key == 'std_truck')

    assert len(shift_sources) == 9
    assert all(item.load_strategy is SqlLoadStrategy.SCOPED for item in shift_sources)
    assert all(item.scope_output_column == 'shift_id' for item in shift_sources)
    assert all(item.materialization_name == 'shift' for item in shift_sources)
    assert all(
        item.partition_dimensions == ('year', 'month', 'day', 'turn') for item in shift_sources
    )
    assert latest.source_table == 'std.StdTruck'
    assert latest.storage_mode is SqlStorageMode.LATEST
    assert latest.load_strategy is SqlLoadStrategy.FULL_SNAPSHOT


def test_shift_info_example_preserves_unmapped_dedupe_contract() -> None:
    from atlanticus.operational_data.processes.dispatch.catalog.examples.tables import shift_info

    assert shift_info.REFERENCE_DEDUPE_COLUMNS == ('shift_id',)
    assert shift_info.DEFINITION.enabled is False


def test_tiempos_example_preserves_functional_last_update() -> None:
    definition = next(item for item in EXAMPLE_DEFINITIONS if item.source_key == 'tiempos_mlp')
    assert definition.source_last_update_output_column == 'moment'
    by_source = {item.source_name: item for item in definition.columns}
    assert by_source['shiftdate'].value_kind is DataValueKind.DATE


def test_catalog_excludes_disabled_sources(monkeypatch) -> None:
    from atlanticus.operational_data.processes.dispatch.catalog import provider

    sql_column = SqlColumnDefinition(
        source_name='Id',
        output_name='id',
        value_kind=DataValueKind.INTEGER,
        required=True,
    )
    enabled = SqlSourceDefinition(
        source_key='enabled_source',
        source_table='dbo.enabled_source',
        storage_mode=SqlStorageMode.LATEST,
        load_strategy=SqlLoadStrategy.FULL_SNAPSHOT,
        columns=(sql_column,),
        enabled=True,
    )
    disabled = SqlSourceDefinition(
        source_key='disabled_source',
        source_table='dbo.disabled_source',
        storage_mode=SqlStorageMode.LATEST,
        load_strategy=SqlLoadStrategy.FULL_SNAPSHOT,
        columns=(sql_column,),
        enabled=False,
    )
    monkeypatch.setattr(provider, 'DEFINITIONS', (enabled, disabled))

    assert provider.build_catalog() == (enabled,)


def test_example_tables_use_canonical_named_column_helper() -> None:
    tables_root = (
        Path(__file__).parents[1]
        / 'src'
        / 'atlanticus'
        / 'operational_data'
        / 'processes'
        / 'dispatch'
        / 'catalog'
        / 'examples'
        / 'tables'
    )
    expected_column_keywords = {'source_name', 'output_name', 'value_kind', 'required'}

    for path in tables_root.glob('*.py'):
        if path.name == '__init__.py':
            continue
        tree = ast.parse(path.read_text())
        source_definitions = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id == 'column':
                assert not node.args, path.name
                assert {item.arg for item in node.keywords} == expected_column_keywords, path.name
            if isinstance(node.func, ast.Name) and node.func.id == 'SqlSourceDefinition':
                source_definitions += 1
                assert not node.args, path.name
                assert 'enabled' in {item.arg for item in node.keywords}, path.name
        assert source_definitions == 1, path.name
