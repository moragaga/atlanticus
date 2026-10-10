from __future__ import annotations

import pytest

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import CARGUIO
from ada.web.application.integrated_operations.modules.dashboard.mine.carguio import runtime
from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.carguio_global_turno import (
    CARGUIO_GLOBAL_TURNO_KPI_KEY,
    map_carguio_global_turno_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.decoder import (
    decode_carguio_store,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.equipos_servicio import (
    EQUIPOS_SERVICIO_KPI_KEY,
    map_equipos_servicio_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.gestion_carguio_turno import (
    GESTION_CARGUIO_TURNO_KPI_KEY,
    map_gestion_carguio_turno_readings,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus

_KEYS = (
    CARGUIO_GLOBAL_TURNO_KPI_KEY,
    EQUIPOS_SERVICIO_KPI_KEY,
    GESTION_CARGUIO_TURNO_KPI_KEY,
)


def _json(value: object) -> dict[str, object]:
    return {
        'status': 'ok',
        'value_kind': 'json',
        'value': value,
        'value_type': None,
        'parsed_value': None,
    }


def _error() -> dict[str, object]:
    return {
        'status': 'error',
        'value_kind': 'json',
        'value': None,
        'value_type': None,
        'parsed_value': None,
    }


@pytest.mark.parametrize(
    ('store', 'expected'),
    [
        (None, DisplayStatus.INVALID),
        ({}, DisplayStatus.NOT_MAPPED),
        ({'latest': None}, DisplayStatus.NOT_MAPPED),
        ({'latest': {'values': []}}, DisplayStatus.INVALID),
        ({'latest': {'values': {}}}, DisplayStatus.NOT_MAPPED),
    ],
)
def test_degraded_source_is_prepared_for_all_three_cards(store, expected):
    prepared = decode_carguio_store(store)
    assert tuple(prepared) == _KEYS
    for mapper in (
        map_carguio_global_turno_readings,
        map_equipos_servicio_readings,
        map_gestion_carguio_turno_readings,
    ):
        state, status = mapper(prepared)
        assert state is None
        assert status is expected


def test_source_error_preserves_legacy_invalid_status():
    prepared = decode_carguio_store(
        {'latest': {'values': {key: _error() for key in _KEYS}}}
    )
    assert all(reading.status is DisplayStatus.INVALID for reading in prepared.values())


def test_each_json_is_independent_and_keeps_its_original_object():
    global_payload = {'data_state': 'unshift', 'rows': []}
    equipos_payload = {'data_state': 'unshift', 'rows': []}
    prepared = decode_carguio_store(
        {
            'latest': {
                'values': {
                    _KEYS[0]: _json(global_payload),
                    _KEYS[1]: _json(equipos_payload),
                }
            }
        }
    )
    assert prepared[_KEYS[0]].value is global_payload
    assert prepared[_KEYS[1]].value is equipos_payload
    assert prepared[_KEYS[2]].status is DisplayStatus.NOT_MAPPED
    assert map_carguio_global_turno_readings(prepared)[1] is DisplayStatus.OK
    assert map_equipos_servicio_readings(prepared)[1] is DisplayStatus.OK
    assert map_gestion_carguio_turno_readings(prepared)[1] is DisplayStatus.NOT_MAPPED


class DashStub:
    def __init__(self):
        self.outputs = None
        self.render = None

    def callback(self, *arguments):
        self.outputs = arguments

        def register(fn):
            self.render = fn
            return fn

        return register


def test_runtime_decodes_once_and_supplies_same_data_to_three_mappers(monkeypatch):
    received = []
    prepared = decode_carguio_store({'latest': {'values': {}}})
    calls = []

    def decode(source):
        calls.append(source)
        return prepared

    def record(source):
        received.append(source)
        return None, DisplayStatus.NOT_MAPPED

    monkeypatch.setattr(runtime, 'decode_carguio_store', decode)
    for name in (
        'map_carguio_global_turno_readings',
        'map_equipos_servicio_readings',
        'map_gestion_carguio_turno_readings',
    ):
        monkeypatch.setattr(runtime, name, record)
    monkeypatch.setattr(runtime, 'build_carguio', lambda **parts: parts)

    dash = DashStub()
    runtime.register_carguio_callback(dash, tool_key='operations')
    assert [item.component_id for item in dash.outputs[:3]] == [
        dashboard_card_content_id('carguio_global_turno'),
        dashboard_card_content_id('equipos_servicio'),
        dashboard_card_content_id('gestion_carguio_turno'),
    ]
    assert dash.outputs[3].component_id == component_kpi_store_id(
        'operations', CARGUIO.tool_component_key
    )
    raw = {'latest': {'values': {}}}
    result = dash.render(raw)
    assert len(result) == 3
    assert calls == [raw]
    assert len(received) == 3
    assert all(item is prepared for item in received)
