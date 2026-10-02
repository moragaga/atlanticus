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
from atlanticus.operational_data.processes.blockgrade.catalog import build_catalog
from atlanticus.operational_data.processes.blockgrade.catalog.definitions import DEFINITIONS
from atlanticus.operational_data.processes.blockgrade.catalog.examples import EXAMPLE_DEFINITIONS
from atlanticus.operational_data.processes.blockgrade.catalog.examples.tables import (
    mms_blockgradebybucket_4hours_d6 as timestamp_reference,
)
from atlanticus.operational_data.processes.blockgrade.errors import BlockgradeCatalogError


def test_catalog_starts_empty_and_requires_configuration() -> None:
    assert DEFINITIONS == ()
    with pytest.raises(BlockgradeCatalogError, match='at least one source'):
        build_catalog()


def test_examples_preserve_real_blockgrade_sources_in_stable_order() -> None:
    assert tuple(item.source_key for item in EXAMPLE_DEFINITIONS) == (
        'mms_blockgradebybucket_4hours_d6',
        'mms_new_blockgrade_details_bucket',
    )


def test_timestamp_window_example_preserves_unmapped_real_contract() -> None:
    definition = EXAMPLE_DEFINITIONS[0]

    assert definition.source_key == 'mms_blockgradebybucket_4hours_d6'
    assert definition.source_table == 'dbo.mms_BlockgradebyBucket_4hours_D6'
    assert definition.storage_mode is SqlStorageMode.LATEST
    assert definition.load_strategy is SqlLoadStrategy.FULL_SNAPSHOT
    assert definition.source_last_update_output_column == 'hra_fin_descarga'
    assert definition.enabled is False
    assert len(definition.columns) == 90
    assert timestamp_reference.TIMESTAMP_COLUMN == 'Hra_FinDescarga'
    assert timestamp_reference.TIMESTAMP_OUTPUT_COLUMN == 'hra_fin_descarga'
    assert timestamp_reference.LOOKBACK_MINUTES == 1500
    assert timestamp_reference.DEDUPE_COLUMNS == ('ddbkey', 'bucket_pk')
    assert timestamp_reference.DEDUPE_ORDER_COLUMNS == ('hra_fin_descarga',)


def test_scoped_example_preserves_real_blockgrade_source() -> None:
    definition = EXAMPLE_DEFINITIONS[1]

    assert definition.source_key == 'mms_new_blockgrade_details_bucket'
    assert definition.source_table == 'dbo.mms_new_blockgradedetailsbucket'
    assert definition.storage_mode is SqlStorageMode.PARTITIONED
    assert definition.load_strategy is SqlLoadStrategy.SCOPED
    assert definition.scope_column == 'shiftindex'
    assert definition.scope_output_column == 'shift_id'
    assert definition.materialization_name == 'shift'
    assert definition.partition_dimensions == ('year', 'month', 'day', 'turn')
    assert definition.enabled is False
    assert len(definition.columns) == 86
    assert definition.required_output_columns == ('shift_id',)

    from atlanticus.operational_data.processes.blockgrade.catalog.examples.tables import (
        mms_new_blockgrade_details_bucket as module,
    )

    assert module.REFERENCE_DEDUPE_COLUMNS == ('shiftindex', 'ddbkey', 'bucket')
    assert module.REFERENCE_DEDUPE_ORDER_COLUMNS == ('shiftindex',)


def test_catalog_excludes_disabled_sources(monkeypatch) -> None:
    from atlanticus.operational_data.processes.blockgrade.catalog import provider

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
        / 'blockgrade'
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
