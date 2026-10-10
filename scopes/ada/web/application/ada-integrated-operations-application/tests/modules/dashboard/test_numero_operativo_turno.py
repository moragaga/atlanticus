from __future__ import annotations

from ada.web.application.integrated_operations.modules.dashboard.mine.transporte.decoder import (
    decode_transporte_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.transporte.numero_operativo_turno import (
    NUMERO_OPERATIVO_TURNO_KPI_KEY,
    build_numero_operativo_turno,
    map_numero_operativo_turno_readings,
)
from ada.web.ui.display_status import DisplayStatus


def _json(value: object) -> dict[str, object]:
    return {
        'status': 'ok', 'value_kind': 'json', 'value': value,
        'value_type': None, 'parsed_value': None,
    }


def _store(value: object) -> dict[str, object]:
    return {'latest': {'values': {NUMERO_OPERATIVO_TURNO_KPI_KEY: _json(value)}}}


def _map(store: object):
    return map_numero_operativo_turno_readings(decode_transporte_store(store))


def _props(component):
    return component.to_plotly_json()['props']


def _walk(component):
    yield component
    children = _props(component).get('children')
    if hasattr(children, 'to_plotly_json'):
        yield from _walk(children)
    elif isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, 'to_plotly_json'):
                yield from _walk(child)


def test_numero_operativo_turno_maps_canonical_values() -> None:
    state, status = _map(_store({'data_state': 'ok', 'values': {
        'efectivos': '38', 'mantencion': '6', 'demora': '3', 'reserva': '2',
    }}))
    assert status is DisplayStatus.OK
    assert state is not None
    assert list(state.as_mapping()) == ['efectivos', 'mantencion', 'demora', 'reserva']


def test_numero_operativo_turno_supports_unshift() -> None:
    state, status = _map(_store({'data_state': 'unshift', 'values': {}}))
    assert status is DisplayStatus.OK
    assert state is not None
    assert state.values == ()


def test_numero_operativo_turno_source_semantics() -> None:
    state, status = _map({'latest': None})
    assert state is None
    assert status is DisplayStatus.NOT_MAPPED
    state, status = _map({'latest': {'values': {
        NUMERO_OPERATIVO_TURNO_KPI_KEY: {
            'status': 'missing', 'value_kind': None, 'value': None,
            'value_type': None, 'parsed_value': None,
        },
    }}})
    assert state is None
    assert status is DisplayStatus.EMPTY


def test_numero_operativo_turno_rejects_missing_value() -> None:
    state, status = _map(_store({'data_state': 'ok', 'values': {
        'efectivos': '38', 'mantencion': '6', 'demora': '3',
    }}))
    assert state is None
    assert status is DisplayStatus.INVALID


def test_numero_operativo_turno_inspects_complete_surface() -> None:
    state, status = _map(_store({'data_state': 'ok', 'values': {
        'efectivos': '38', 'mantencion': '6', 'demora': '3', 'reserva': '2',
    }}))
    component = build_numero_operativo_turno(state, status)
    inspection_nodes = [
        node for node in _walk(component) if _props(node).get('data-kpi-inspection-key') is not None
    ]
    assert len(inspection_nodes) == 1
    assert _props(inspection_nodes[0])['data-kpi-inspection-key'] == NUMERO_OPERATIVO_TURNO_KPI_KEY
