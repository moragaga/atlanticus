from __future__ import annotations

from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.decoder import (
    decode_general_mina_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.mp10 import (
    MP10_HOTEL_MINA_INST_KPI_KEY,
    MP10_HOTEL_MINA_PROY_KPI_KEY,
    build_mp10,
    map_mp10_readings,
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


def _store(values: dict[str, object]) -> dict[str, object]:
    return {'latest': {'values': values}}


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


def test_mp10_maps_independent_json_contracts() -> None:
    state = map_mp10_readings(
        decode_general_mina_store(
            _store(
                {
                    MP10_HOTEL_MINA_INST_KPI_KEY: _json(
                        {'value': '275', 'alert': 'Alerta 2', 'status': '2'}
                    ),
                    MP10_HOTEL_MINA_PROY_KPI_KEY: _json(
                        {'value': '420', 'alert': 'Alerta 3', 'status': '1'}
                    ),
                }
            )
        )
    )
    assert state.instant is not None
    assert state.instant.value == '275'
    assert state.instant.alert == 'Alerta 2'
    assert state.instant.status is DashboardValueStatus.WARNING
    assert state.projection is not None
    assert state.projection.status is DashboardValueStatus.DANGER


def test_mp10_keeps_source_states_independent() -> None:
    state = map_mp10_readings(
        decode_general_mina_store(
            _store(
                {MP10_HOTEL_MINA_PROY_KPI_KEY: _json({'value': '148', 'alert': None, 'status': None})}
            )
        )
    )
    assert state.instant is None
    assert state.instant_status is DisplayStatus.NOT_MAPPED
    assert state.projection is not None
    assert state.projection_status is DisplayStatus.OK


def test_mp10_rejects_invalid_json_contract_without_collapsing_other_kpi() -> None:
    state = map_mp10_readings(
        decode_general_mina_store(
            _store(
                {
                    MP10_HOTEL_MINA_INST_KPI_KEY: _json(
                        {'value': '275', 'alert': 'Alerta 2', 'status': 'unexpected'}
                    ),
                    MP10_HOTEL_MINA_PROY_KPI_KEY: _json(
                        {'value': '420', 'alert': 'Alerta 3', 'status': '1'}
                    ),
                }
            )
        )
    )
    assert state.instant is None
    assert state.instant_status is DisplayStatus.INVALID
    assert state.projection is not None
    assert state.projection_status is DisplayStatus.OK


def test_mp10_places_inspection_key_only_on_each_value_surface() -> None:
    state = map_mp10_readings(
        decode_general_mina_store(
            _store(
                {
                    MP10_HOTEL_MINA_INST_KPI_KEY: _json(
                        {'value': '275', 'alert': 'Alerta 2', 'status': '2'}
                    ),
                    MP10_HOTEL_MINA_PROY_KPI_KEY: _json(
                        {'value': '420', 'alert': 'Alerta 3', 'status': '1'}
                    ),
                }
            )
        )
    )
    component = build_mp10(state)
    nodes = tuple(_walk(component))
    inspection_nodes = [
        node for node in nodes if _props(node).get('data-kpi-inspection-key') is not None
    ]

    assert [_props(node)['data-kpi-inspection-key'] for node in inspection_nodes] == [
        MP10_HOTEL_MINA_INST_KPI_KEY,
        MP10_HOTEL_MINA_PROY_KPI_KEY,
    ]
    assert all('mp10__value' in _props(node).get('className', '') for node in inspection_nodes)
