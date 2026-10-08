from __future__ import annotations

from ada.web.application.integrated_operations.modules.dashboard.mine.transporte.transporte_global_turno import (
    TRANSPORTE_GLOBAL_TURNO_KPI_KEY,
    build_transporte_global_turno,
    map_transporte_global_turno_store,
)
from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.ui.display_status import DisplayStatus


def _metric(value: object, status: object) -> dict[str, object]:
    return {'value': value, 'status': status}


def _row(
    key: str,
    real: object,
    real_status: object,
    plan: object,
    plan_status: object,
) -> dict[str, object]:
    return {
        'key': key,
        'real': _metric(real, real_status),
        'plan': _metric(plan, plan_status),
    }


def _json(value: object) -> dict[str, object]:
    return {'status': 'ok', 'value_kind': 'json', 'value': value}


def _store(value: object) -> dict[str, object]:
    return {
        'latest': {
            'values': {
                TRANSPORTE_GLOBAL_TURNO_KPI_KEY: _json(value),
            }
        }
    }


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


def _payload() -> dict[str, object]:
    return {
        'data_state': 'ok',
        'rows': [
            _row('distancia_media', '5.8', '2', '5.5', None),
            _row('rendimiento', '2450', '2', '2600', None),
            _row('ciclo', '31', '1', '29', '2'),
            _row('uebd', '72', None, '75', '1'),
            _row('velocidad_media', '24.5', None, '25.0', None),
        ],
    }


def test_transporte_global_turno_uses_canonical_frontend_order() -> None:
    state, status = map_transporte_global_turno_store(_store(_payload()))

    assert status is DisplayStatus.OK
    assert state is not None
    assert [row.key for row in state.rows] == [
        'rendimiento',
        'uebd',
        'ciclo',
        'velocidad_media',
        'distancia_media',
    ]


def test_transporte_global_turno_preserves_independent_real_plan_statuses() -> None:
    state, status = map_transporte_global_turno_store(_store(_payload()))

    assert status is DisplayStatus.OK
    assert state is not None
    values = {row.key: row for row in state.rows}
    assert values['rendimiento'].real.status is DashboardValueStatus.WARNING
    assert values['rendimiento'].plan.status is DashboardValueStatus.NEUTRAL
    assert values['ciclo'].real.status is DashboardValueStatus.DANGER
    assert values['ciclo'].plan.status is DashboardValueStatus.WARNING
    assert values['uebd'].real.status is DashboardValueStatus.NEUTRAL
    assert values['uebd'].plan.status is DashboardValueStatus.DANGER


def test_transporte_global_turno_supports_unshift() -> None:
    state, status = map_transporte_global_turno_store(
        _store({'data_state': 'unshift', 'rows': []})
    )

    assert status is DisplayStatus.OK
    assert state is not None
    assert state.rows == ()


def test_transporte_global_turno_source_semantics() -> None:
    state, status = map_transporte_global_turno_store({'latest': None})
    assert state is None
    assert status is DisplayStatus.NOT_MAPPED

    state, status = map_transporte_global_turno_store(
        {
            'latest': {
                'values': {
                    TRANSPORTE_GLOBAL_TURNO_KPI_KEY: {
                        'status': 'missing',
                        'value_kind': None,
                        'value': None,
                    }
                }
            }
        }
    )
    assert state is None
    assert status is DisplayStatus.EMPTY


def test_transporte_global_turno_inspects_complete_surface() -> None:
    state, status = map_transporte_global_turno_store(_store(_payload()))
    component = build_transporte_global_turno(state, status)
    inspection_nodes = [
        node
        for node in _walk(component)
        if _props(node).get('data-kpi-inspection-key') is not None
    ]

    assert len(inspection_nodes) == 1
    assert (
        _props(inspection_nodes[0])['data-kpi-inspection-key']
        == TRANSPORTE_GLOBAL_TURNO_KPI_KEY
    )
