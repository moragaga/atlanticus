from datetime import UTC, datetime

import pytest

from ada.kpis.core import KpiArea, KpiCatalog, KpiMode, KpiSpec, KpiWatermark
from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataPartition,
    DataRequirement,
    DataSource,
)


def test_simple_spec_projects_typed_requirement() -> None:
    column = DataColumn('tag', DataColumnType.FLOAT)
    spec = KpiSpec(
        key='kpi-a',
        area=KpiArea.GENERAL,
        mode=KpiMode.LATEST_NUMBER,
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.LATEST,
        columns=(column,),
        decimals=2,
    )
    assert spec.area == 'general'
    assert spec.requirements == (
        DataRequirement(
            source=DataSource.PI_INTERPOLATED,
            partition=DataPartition.LATEST,
            columns=(column,),
        ),
    )


def test_numeric_mode_rejects_text_column() -> None:
    with pytest.raises(ValueError, match='unsupported column types'):
        KpiSpec(
            key='kpi-a',
            area='general',
            mode=KpiMode.SUM,
            source=DataSource.PI_INTERPOLATED,
            partition=DataPartition.DAILY,
            columns=(DataColumn('tag', DataColumnType.TEXT),),
        )


def test_custom_spec_uses_shared_requirements_without_kpi_source_aliases() -> None:
    requirement = DataRequirement(
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.LATEST,
        columns=(DataColumn('tag', DataColumnType.FLOAT),),
    )
    spec = KpiSpec(
        key='custom',
        area='general',
        mode=KpiMode.CUSTOM,
        source_requirements=(requirement,),
        custom_resolver=lambda context: 1,
    )
    assert spec.requirements == (requirement,)


def test_catalog_rejects_duplicate_keys() -> None:
    column = DataColumn('tag', DataColumnType.FLOAT)
    spec = KpiSpec(
        key='kpi-a',
        area='general',
        mode=KpiMode.LATEST_NUMBER,
        source=DataSource.PI_INTERPOLATED,
        partition=DataPartition.LATEST,
        columns=(column,),
    )
    with pytest.raises(ValueError, match='unique'):
        KpiCatalog((spec, spec))


def test_watermark_requires_second_precision() -> None:
    with pytest.raises(ValueError, match='second precision'):
        KpiWatermark(datetime(2026, 8, 31, 12, 0, 0, 1, tzinfo=UTC))
