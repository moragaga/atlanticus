from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    STOCKPILE_CHACAY,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.decoder import (
    decode_stockpile_chacay_store,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.runtime import (
    register_stockpile_chacay_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.tendencia_alimentado.definitions import (
    ALIMENTADO_TRENDS,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.tendencia_alimentado.mapper import (
    map_tendencia_alimentado_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.tendencia_alimentado.presentation import (
    build_tendencia_alimentado,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus

_END = datetime(2026, 4, 5, 4, 0, tzinfo=UTC)
_START = _END - timedelta(hours=1)


def _map_trend(store):
    readings, timeseries = decode_stockpile_chacay_store(store)
    return map_tendencia_alimentado_readings(readings, timeseries)


def _time_entry(values: list[object], *, value_type: str = 'float') -> dict[str, object]:
    return {
        'hours': 1,
        'start_utc': _START.isoformat(),
        'end_utc': _END.isoformat(),
        'value_type': value_type,
        'values': values,
    }


def _store() -> dict[str, object]:
    series = {
        definition.kpi_key: _time_entry([float(i) for i in range(30)])
        for definition in ALIMENTADO_TRENDS
    }
    latest = {
        definition.kpi_key: {
            'status': 'ok',
            'value_kind': 'value',
            'value': str(str(i + 10)),
            'value_type': 'text',
            'parsed_value': str(str(i + 10)),
        }
        for i, definition in enumerate(ALIMENTADO_TRENDS)
    }
    return {
        'timeseries': {'end_utc': _END.isoformat(), 'step_seconds': 120, 'series': series},
        'latest': {'values': latest},
    }


def _walk(item):
    if isinstance(item, Component):
        yield item
        yield from _walk(getattr(item, 'children', None))
    elif isinstance(item, list | tuple):
        for child in item:
            yield from _walk(child)


def test_three_legacy_keys_use_current_component_timeseries_contract():
    assert [definition.kpi_key for definition in ALIMENTADO_TRENDS] == [
        'axb_alimentado_hora',
        'recuperacion_cu_alimentado_hora',
        'ley_cu_alimentado_hora',
    ]
    readings = _map_trend(_store())
    assert len(readings) == 3
    for reading in readings:
        assert reading.history.status is DisplayStatus.OK
        assert len(reading.history.points) == 30
        assert reading.history.points[0].timestamp_utc == _START + timedelta(minutes=2)
        assert reading.history.points[-1].timestamp_utc == _END
    assert [reading.current.value for reading in readings] == ['10', '11', '12']


def test_nulls_preserved_and_all_null_series_is_a_blank_graph():
    data = _store()
    key = ALIMENTADO_TRENDS[0].kpi_key
    data['timeseries']['series'][key]['values'][3] = None
    assert _map_trend(data)[0].history.points[3].value is None
    data['timeseries']['series'][key]['values'] = [None] * 30
    history = _map_trend(data)[0].history
    assert history.status is DisplayStatus.OK
    assert len(history.points) == 30
    assert all(point.value is None for point in history.points)


def test_samples_are_not_reformatted_or_imputed_by_the_mapper():
    data = _store()
    key = ALIMENTADO_TRENDS[0].kpi_key
    data['timeseries']['series'][key]['value_type'] = 'integer'
    data['timeseries']['series'][key]['values'] = [None, 0, 11] + [5] * 27
    history = _map_trend(data)[0].history
    assert history.status is DisplayStatus.OK
    assert [point.value for point in history.points[:3]] == [None, 0, 11]
    assert type(history.points[1].value) is int


def test_string_samples_are_not_coerced_to_numeric_values():
    data = _store()
    key = ALIMENTADO_TRENDS[0].kpi_key
    data['timeseries']['series'][key]['values'][0] = '11.25'
    history = _map_trend(data)[0].history
    assert history.status is DisplayStatus.INVALID


@pytest.mark.parametrize(
    'bad',
    [
        {'hours': 2},
        {'value_type': 'boolean'},
        {'values': [1]},
        {'values': [True] * 30},
    ],
)
def test_invalid_series_does_not_change_independent_readings(bad):
    data = _store()
    key = ALIMENTADO_TRENDS[0].kpi_key
    data['timeseries']['series'][key].update(bad)
    readings = _map_trend(data)
    assert readings[0].history.status is DisplayStatus.INVALID
    assert readings[1].history.status is DisplayStatus.OK
    assert readings[2].history.status is DisplayStatus.OK


def test_missing_individual_series_and_absent_sources_keep_statuses():
    data = _store()
    del data['timeseries']['series'][ALIMENTADO_TRENDS[0].kpi_key]
    assert _map_trend(data)[0].history.status is DisplayStatus.NOT_MAPPED
    readings = _map_trend(None)
    assert all(reading.current.status is DisplayStatus.NOT_MAPPED for reading in readings)
    assert all(reading.history.status is DisplayStatus.NOT_MAPPED for reading in readings)


def test_inspection_targets_and_headers_preserve_three_kpi_keys():
    rendered = build_tendencia_alimentado(_map_trend(_store()))
    targets = [item for item in _walk(rendered) if hasattr(item, 'data-kpi-inspection-key')]
    assert [getattr(item, 'data-kpi-inspection-key') for item in targets] == [
        definition.kpi_key for definition in ALIMENTADO_TRENDS
    ]
    assert all(target.role == 'button' and target.tabIndex == 0 for target in targets)


class DashStub:
    def __init__(self) -> None:
        self.args = None
        self.refresh = None

    def callback(self, *args):
        self.args = args

        def register(fn):
            self.refresh = fn
            return fn

        return register


def test_callback_consumes_existing_plant_component_store():
    app = DashStub()
    register_stockpile_chacay_callback(app, tool_key='integrated_operations')
    assert app.args[0].component_id == dashboard_card_content_id('stockpile_chacay')
    assert app.args[1].component_id == dashboard_card_content_id('tendencia_alimentado')
    assert app.args[2].component_id == component_kpi_store_id(
        'integrated_operations', STOCKPILE_CHACAY.tool_component_key
    )
    result = app.refresh(_store())
    assert len(result) == 2
    assert isinstance(result[0], Component)
    assert isinstance(result[1], Component)
