from __future__ import annotations

import pytest

from ada.kpis.core import (
    KpiArea,
    KpiMode,
    KpiResult,
    KpiSpec,
    KpiStatus,
    KpiValueKind,
)
from atlanticus.operational_data.core import (
    DataColumn,
    DataColumnType,
    DataInputSpec,
    DataSource,
    DataView,
)


def _input() -> DataInputSpec:
    return DataInputSpec(
        input_key='value',
        source=DataSource.PI_INTERPOLATED,
        view=DataView.LATEST,
        columns=(DataColumn('tag', DataColumnType.FLOAT),),
    )


def test_json_spec_can_declare_structural_empty_payload() -> None:
    spec = KpiSpec(
        key='dynamic-table',
        area=KpiArea.GENERAL,
        mode=KpiMode.CUSTOM,
        inputs=(_input(),),
        custom_resolver=lambda _context: {'rows': [1]},
        value_kind=KpiValueKind.JSON,
        empty_json={'rows': [], 'columns': []},
    )
    assert spec.empty_json == {'rows': [], 'columns': []}


def test_value_spec_rejects_empty_json() -> None:
    with pytest.raises(ValueError, match='must not declare empty_json'):
        KpiSpec(
            key='scalar',
            area=KpiArea.GENERAL,
            mode=KpiMode.CONSTANT,
            constant_value=1,
            empty_json={},
        )


def test_degraded_json_result_preserves_structural_value() -> None:
    missing = KpiResult(
        KpiStatus.MISSING,
        KpiValueKind.JSON,
        value={'rows': []},
    )
    error = KpiResult(
        KpiStatus.ERROR,
        KpiValueKind.JSON,
        value={'rows': []},
        error='RuntimeError',
    )
    assert missing.value == {'rows': []}
    assert error.value == {'rows': []}
