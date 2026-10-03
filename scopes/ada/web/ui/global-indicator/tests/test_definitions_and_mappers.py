import pytest
from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus
from ada.web.ui.global_indicator import (
    GlobalIndicatorDefinition,
    GlobalIndicatorDefinitionError,
    GlobalIndicatorLastMeasurementDefinition,
    GlobalIndicatorMeasurementDefinition,
    global_indicator_kpi_keys,
    map_global_indicator,
    map_global_indicators,
)


def _definition(key: str = 'movimiento_mina') -> GlobalIndicatorDefinition:
    return GlobalIndicatorDefinition(
        key=key,
        label='Movimiento Mina',
        unit='ktms',
        measurements=(
            GlobalIndicatorMeasurementDefinition(
                key='turno',
                label='Turno',
                actual_kpi_key=f'{key}.turno.actual',
                plan_kpi_key=f'{key}.turno.plan',
                color_kpi_key=f'{key}.turno.color',
            ),
            GlobalIndicatorMeasurementDefinition(
                key='dia',
                label='Día',
                actual_kpi_key=f'{key}.dia.actual',
                plan_kpi_key=f'{key}.dia.plan',
                color_kpi_key=f'{key}.dia.color',
            ),
        ),
        last_measurement=GlobalIndicatorLastMeasurementDefinition(
            kpi_key=f'{key}.latest',
        ),
    )


def _values(key: str = 'movimiento_mina') -> dict[str, object]:
    return {
        f'{key}.turno.actual': '120,3',
        f'{key}.turno.plan': '125,0',
        f'{key}.turno.color': 'indicator-positive',
        f'{key}.dia.actual': '240,2',
        f'{key}.dia.plan': '250,0',
        f'{key}.dia.color': 'indicator-warning',
        f'{key}.latest': '121,0',
    }


def test_definition_exposes_all_required_kpi_keys_in_stable_order() -> None:
    assert _definition().kpi_keys == (
        'movimiento_mina.turno.actual',
        'movimiento_mina.turno.plan',
        'movimiento_mina.turno.color',
        'movimiento_mina.dia.actual',
        'movimiento_mina.dia.plan',
        'movimiento_mina.dia.color',
        'movimiento_mina.latest',
    )


def test_collection_kpi_keys_deduplicate_without_reordering() -> None:
    first = _definition('movimiento_mina')
    second = GlobalIndicatorDefinition(
        key='transportado',
        label='Transportado',
        unit='ktms',
        measurements=(
            GlobalIndicatorMeasurementDefinition(
                key='turno',
                label='Turno',
                actual_kpi_key='shared.actual',
                plan_kpi_key='transportado.turno.plan',
            ),
            GlobalIndicatorMeasurementDefinition(
                key='dia',
                label='Día',
                actual_kpi_key='shared.actual',
                plan_kpi_key='transportado.dia.plan',
            ),
        ),
    )

    keys = global_indicator_kpi_keys((first, second))

    assert keys[-3:] == (
        'shared.actual',
        'transportado.turno.plan',
        'transportado.dia.plan',
    )
    assert keys.count('shared.actual') == 1


def test_mapper_builds_existing_runtime_state_and_preserves_inspection_keys() -> None:
    state = map_global_indicator(definition=_definition(), values=_values())

    assert state.key == 'movimiento_mina'
    assert state.measurements[0].actual_value.value == '120,3'
    assert state.measurements[0].plan_value.value == '125,0'
    assert state.measurements[0].color_class == 'indicator-positive'
    assert state.measurements[0].actual_kpi_key == 'movimiento_mina.turno.actual'
    assert state.measurements[0].plan_kpi_key == 'movimiento_mina.turno.plan'
    assert state.last_measurement is not None
    assert state.last_measurement.actual_kpi_key == 'movimiento_mina.latest'


def test_mapper_accepts_ready_dash_status_component_without_interpreting_it() -> None:
    values = _values()
    values['movimiento_mina.turno.actual'] = html.Img(src='/status/error.svg')

    state = map_global_indicator(definition=_definition(), values=values)

    resolved = state.measurements[0].actual_value
    assert resolved.status is DisplayStatus.OK
    assert isinstance(resolved.value, Component)


def test_mapper_requires_every_declared_kpi_instead_of_converting_missing_binding_to_empty() -> (
    None
):
    values = _values()
    del values['movimiento_mina.dia.plan']

    with pytest.raises(KeyError, match='movimiento_mina.dia.plan'):
        map_global_indicator(definition=_definition(), values=values)


def test_mapper_requires_declared_color_kpi() -> None:
    values = _values()
    del values['movimiento_mina.dia.color']

    with pytest.raises(KeyError, match='movimiento_mina.dia.color'):
        map_global_indicator(
            definition=_definition(),
            values=values,
        )


def test_collection_mapper_preserves_definition_order() -> None:
    first = _definition('movimiento_mina')
    second = _definition('transportado')
    values = {**_values('movimiento_mina'), **_values('transportado')}

    collection = map_global_indicators(definitions=(first, second), values=values)

    assert tuple(indicator.key for indicator in collection) == (
        'movimiento_mina',
        'transportado',
    )


def test_definition_rejects_duplicate_measurement_keys() -> None:
    measurement = GlobalIndicatorMeasurementDefinition(
        key='dia',
        label='Día',
        actual_kpi_key='a',
        plan_kpi_key='b',
    )

    with pytest.raises(GlobalIndicatorDefinitionError, match='duplicate measurement keys'):
        GlobalIndicatorDefinition(
            key='produccion',
            label='Producción',
            unit='kt',
            measurements=(measurement, measurement),
        )


def test_definition_rejects_empty_kpi_binding() -> None:
    with pytest.raises(GlobalIndicatorDefinitionError, match='actual_kpi_key cannot be empty'):
        GlobalIndicatorMeasurementDefinition(
            key='dia',
            label='Día',
            actual_kpi_key='   ',
            plan_kpi_key='produccion.dia.plan',
        )
