from __future__ import annotations

from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.carguio_global_turno import (
    CARGUIO_GLOBAL_TURNO_KPI_KEY,
    build_carguio_global_turno,
    map_carguio_global_turno_store,
)
from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.ui.display_status import DisplayStatus


def _json(value: object) -> dict[str, object]:
    return {
        'status': 'ok',
        'value_kind': 'json',
        'value': value,
        'value_type': None,
        'parsed_value': None,
    }


def _store(value: object) -> dict[str, object]:
    return {
        'latest': {
            'values': {
                CARGUIO_GLOBAL_TURNO_KPI_KEY: _json(value),
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


def test_carguio_global_turno_maps_backend_rows_without_calculating_total() -> None:
    state, status = map_carguio_global_turno_store(
        _store(
            {
                'data_state': 'ok',
                'rows': [
                    {
                        'flota': 'PA',
                        'is_total': False,
                        'op_req': _comparison('8', '10', '2'),
                        'disponibilidad': _comparison('85', '90', '0'),
                        'uebd': _comparison('72', '75', None),
                        'rendimiento': _comparison('2.450', '2.600', '1'),
                    },
                    {
                        'flota': 'TOTAL',
                        'is_total': True,
                        'op_req': _comparison('14', '17', '2'),
                        'disponibilidad': _comparison('173', '182', None),
                        'uebd': _comparison('146', '153', None),
                        'rendimiento': _comparison('4.550', '4.900', '1'),
                    },
                ],
            }
        )
    )

    assert status is DisplayStatus.OK
    assert state is not None
    assert [row.flota for row in state.rows] == ['PA', 'TOTAL']
    assert state.rows[1].is_total is True
    assert state.rows[0].op_req.status is DashboardValueStatus.WARNING
    assert state.rows[0].rendimiento.status is DashboardValueStatus.DANGER
    assert state.rows[1].op_req.real == '14'


def test_carguio_global_turno_supports_unshift_without_rows() -> None:
    state, status = map_carguio_global_turno_store(_store({'data_state': 'unshift', 'rows': []}))

    assert status is DisplayStatus.OK
    assert state is not None
    assert state.rows == ()


def test_carguio_global_turno_rejects_missing_status() -> None:
    state, status = map_carguio_global_turno_store(
        _store(
            {
                'data_state': 'ok',
                'rows': [
                    {
                        'flota': 'PA',
                        'is_total': False,
                        'op_req': {'real': '8', 'plan': '10'},
                        'disponibilidad': _comparison('85', '90', '0'),
                        'uebd': _comparison('72', '75', None),
                        'rendimiento': _comparison('2.450', '2.600', '1'),
                    }
                ],
            }
        )
    )

    assert state is None
    assert status is DisplayStatus.INVALID


def test_carguio_global_turno_inspects_complete_json_surface() -> None:
    state, status = map_carguio_global_turno_store(_store({'data_state': 'unshift', 'rows': []}))
    component = build_carguio_global_turno(state, status)
    inspection_nodes = [
        node for node in _walk(component) if _props(node).get('data-kpi-inspection-key') is not None
    ]

    assert len(inspection_nodes) == 1
    assert _props(inspection_nodes[0])['data-kpi-inspection-key'] == CARGUIO_GLOBAL_TURNO_KPI_KEY
