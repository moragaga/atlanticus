from __future__ import annotations

from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.equipos_servicio import (
    EQUIPOS_SERVICIO_KPI_KEY,
    build_equipos_servicio,
    map_equipos_servicio_store,
)
from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.ui.display_status import DisplayStatus


def _json(value: object) -> dict[str, object]:
    return {'status': 'ok', 'value_kind': 'json', 'value': value}


def _store(value: object) -> dict[str, object]:
    return {
        'latest': {
            'values': {
                EQUIPOS_SERVICIO_KPI_KEY: _json(value),
            }
        }
    }


def _comparison(
    real: object,
    plan: object,
    status: object,
) -> dict[str, object]:
    return {'real': real, 'plan': plan, 'status': status}


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


def test_equipos_servicio_preserves_backend_rows_and_total() -> None:
    state, status = map_equipos_servicio_store(
        _store(
            {
                'data_state': 'ok',
                'rows': [
                    {
                        'equipo': 'Bulldozer',
                        'is_total': False,
                        'operando': _comparison('3', '4', None),
                        'disponibles': _comparison('5', '6', '2'),
                        'fuera_servicio': _comparison('1', '1', '1'),
                    },
                    {
                        'equipo': 'TOTAL',
                        'is_total': True,
                        'operando': _comparison('15', '18', '1'),
                        'disponibles': _comparison('25', '28', None),
                        'fuera_servicio': _comparison('4', '3', '0'),
                    },
                ],
            }
        )
    )

    assert status is DisplayStatus.OK
    assert state is not None
    assert [row.equipo for row in state.rows] == ['Bulldozer', 'TOTAL']
    assert state.rows[1].is_total is True
    assert state.rows[0].disponibles.status is DashboardValueStatus.WARNING
    assert state.rows[0].fuera_servicio.status is DashboardValueStatus.DANGER
    assert state.rows[1].operando.real == '15'


def test_equipos_servicio_supports_unshift_without_rows() -> None:
    state, status = map_equipos_servicio_store(
        _store({'data_state': 'unshift', 'rows': []})
    )

    assert status is DisplayStatus.OK
    assert state is not None
    assert state.rows == ()


def test_equipos_servicio_rejects_missing_status() -> None:
    state, status = map_equipos_servicio_store(
        _store(
            {
                'data_state': 'ok',
                'rows': [
                    {
                        'equipo': 'Bulldozer',
                        'is_total': False,
                        'operando': {'real': '3', 'plan': '4'},
                        'disponibles': _comparison('5', '6', None),
                        'fuera_servicio': _comparison('1', '1', None),
                    }
                ],
            }
        )
    )

    assert state is None
    assert status is DisplayStatus.INVALID


def test_equipos_servicio_inspects_complete_json_surface() -> None:
    state, status = map_equipos_servicio_store(
        _store({'data_state': 'unshift', 'rows': []})
    )
    component = build_equipos_servicio(state, status)
    inspection_nodes = [
        node
        for node in _walk(component)
        if _props(node).get('data-kpi-inspection-key') is not None
    ]

    assert len(inspection_nodes) == 1
    assert (
        _props(inspection_nodes[0])['data-kpi-inspection-key']
        == EQUIPOS_SERVICIO_KPI_KEY
    )
