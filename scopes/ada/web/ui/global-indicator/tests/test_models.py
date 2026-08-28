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


def test_measurement_values_accept_independent_optional_kpi_keys() -> None:
    state = GlobalIndicatorMeasurementState(
        key='turno',
        label='Turno',
        actual_value='89,4',
        plan_value='90,5',
        actual_kpi_key='  recovery.shift.actual  ',
        plan_kpi_key='  recovery.shift.plan  ',
    )

    assert state.actual_kpi_key == 'recovery.shift.actual'
    assert state.plan_kpi_key == 'recovery.shift.plan'


def test_last_measurement_accepts_its_own_optional_kpi_key() -> None:
    state = GlobalIndicatorLastMeasurementState(
        '88,9',
        actual_kpi_key='  recovery.latest  ',
    )

    assert state.actual_kpi_key == 'recovery.latest'


@pytest.mark.parametrize('field_name', ['actual_kpi_key', 'plan_kpi_key'])
def test_measurement_rejects_empty_value_kpi_key(field_name: str) -> None:
    kwargs = {field_name: '   '}
    with pytest.raises(GlobalIndicatorDefinitionError, match=f'{field_name} cannot be empty'):
        GlobalIndicatorMeasurementState(
            key='turno',
            label='Turno',
            actual_value='89,4',
            plan_value='90,5',
            **kwargs,
        )


def test_last_measurement_rejects_empty_value_kpi_key() -> None:
    with pytest.raises(GlobalIndicatorDefinitionError, match='actual_kpi_key cannot be empty'):
        GlobalIndicatorLastMeasurementState('88,9', actual_kpi_key='   ')
