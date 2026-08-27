import pytest

from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.global_indicator import (
    GlobalIndicatorCollection,
    GlobalIndicatorDefinitionError,
    GlobalIndicatorLastMeasurementState,
    GlobalIndicatorMeasurementState,
    GlobalIndicatorState,
    global_indicator_measurement_capacity,
)


def _measurement(key: str, label: str, actual='89,4', plan='90,5'):
    return GlobalIndicatorMeasurementState(
        key=key,
        label=label,
        actual_value=actual,
        plan_value=plan,
    )


def test_measurements_coerce_shared_display_status_values() -> None:
    state = _measurement(
        'dia',
        'Día',
        actual=DisplayValue.invalid(),
        plan=None,
    )

    assert state.actual_value.status is DisplayStatus.INVALID
    assert state.plan_value.status is DisplayStatus.EMPTY


def test_global_indicator_preserves_standard_measurement_capacity() -> None:
    state = GlobalIndicatorState(
        key='recuperacion_cu',
        label='Recuperación Cu',
        unit='%',
        measurements=(
            _measurement('turno', 'Turno'),
            _measurement('dia', 'Día'),
            _measurement('semana', 'Semana'),
        ),
        last_measurement=GlobalIndicatorLastMeasurementState('88,9'),
    )

    assert global_indicator_measurement_capacity() == 3
    assert state.all_measurement_keys == ('turno', 'dia', 'semana', 'latest')


def test_global_indicator_rejects_measurement_counts_outside_visual_standard() -> None:
    with pytest.raises(GlobalIndicatorDefinitionError, match='two or three measurements'):
        GlobalIndicatorState(
            key='recuperacion_cu',
            label='Recuperación Cu',
            unit='%',
            measurements=(_measurement('dia', 'Día'),),
        )


def test_collection_rejects_duplicate_indicator_keys() -> None:
    indicator = GlobalIndicatorState(
        key='recuperacion_cu',
        label='Recuperación Cu',
        unit='%',
        measurements=(
            _measurement('turno', 'Turno'),
            _measurement('dia', 'Día'),
        ),
    )

    with pytest.raises(GlobalIndicatorDefinitionError, match='duplicate keys'):
        GlobalIndicatorCollection((indicator, indicator))
