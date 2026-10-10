from __future__ import annotations

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    STOCKPILE_CHACAY,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay import (
    decoder,
    runtime,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.decoder import (
    decode_stockpile_chacay_store,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.feeders import (
    STOCKPILE_CHACAY_FEEDER_GROUPS,
    ChacayFeederDefinition,
    map_chacay_feeders_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.stockpile import (
    STOCKPILE_CHACAY_PILES,
    STOCKPILE_CHACAY_POSITION_KEY,
    STOCKPILE_CHACAY_ROWS,
    map_stockpile_chacay_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.tendencia_alimentado import (
    map_tendencia_alimentado_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.tendencia_alimentado.definitions import (
    ALIMENTADO_TRENDS,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus
from ada.web.ui.feeder import FeederColor


def _entry(value: object) -> dict[str, object]:
    return {
        'status': 'ok',
        'value_kind': 'value',
        'value': str(value),
        'value_type': 'text',
        'parsed_value': str(value),
    }


def test_latest_is_decoded_once_per_distinct_key(monkeypatch):
    calls = []
    original = decoder.decode_kpi_latest_value

    def tracked(value, *, present):
        calls.append((value, present))
        return original(value, present=present)

    monkeypatch.setattr(decoder, 'decode_kpi_latest_value', tracked)
    values, timeseries = decode_stockpile_chacay_store({'latest': {'values': {}}})
    assert timeseries is None
    assert len(values) == 28
    assert len(calls) == 28
    assert all(not present for _, present in calls)
    assert all(reading.status is DisplayStatus.NOT_MAPPED for reading in values.values())


def test_stockpile_and_trend_preserve_distinct_missing_store_semantics():
    values, timeseries = decode_stockpile_chacay_store(None)
    stockpile = map_stockpile_chacay_readings(values)
    tendencia = map_tendencia_alimentado_readings(values, timeseries)
    assert stockpile.position.status is DisplayStatus.INVALID
    assert all(pile.percent.status is DisplayStatus.INVALID for pile in stockpile.piles)
    assert all(item.current.status is DisplayStatus.NOT_MAPPED for item in tendencia)
    assert all(item.history.status is DisplayStatus.NOT_MAPPED for item in tendencia)


def test_original_and_parsed_representations_remain_independent():
    pile_key = STOCKPILE_CHACAY_PILES[0].kpi_key
    feeder_key = STOCKPILE_CHACAY_FEEDER_GROUPS[0][0].value_kpi_key
    trend_key = ALIMENTADO_TRENDS[0].kpi_key
    raw = {
        'latest': {
            'values': {
                STOCKPILE_CHACAY_POSITION_KEY: _entry('2'),
                pile_key: {**_entry('65'), 'parsed_value': ' 65,0 '},
                feeder_key: {**_entry('20.25'), 'parsed_value': '20,25'},
                trend_key: _entry('7.2'),
            }
        },
        'timeseries': {'series': {}},
    }
    values, timeseries = decode_stockpile_chacay_store(raw)
    stockpile = map_stockpile_chacay_readings(values)
    trend = map_tendencia_alimentado_readings(values, timeseries)
    assert stockpile.position.value == 2
    assert stockpile.piles[0].percent.value == '65,0'
    assert str(stockpile.feeders[0][0].value.value) == '20.25'
    assert trend[0].current.value == '7.2'
    assert trend[0].history.status is DisplayStatus.NOT_MAPPED
    assert timeseries is raw['timeseries']


def test_optional_feeder_color_is_prepared_with_configured_key():
    feeder_key = STOCKPILE_CHACAY_FEEDER_GROUPS[0][0].value_kpi_key
    groups = ((ChacayFeederDefinition(feeder_key, 'color_example'),),)
    values, _ = decode_stockpile_chacay_store(
        {'latest': {'values': {feeder_key: _entry('12'), 'color_example': _entry('2')}}},
        feeder_definitions=groups,
    )
    reading = map_chacay_feeders_readings(values, groups)[0][0]
    assert reading.color is FeederColor.WARNING
    assert str(reading.value.value) == '12'


class DashStub:
    def __init__(self):
        self.args = None
        self.render = None
        self.callback_count = 0

    def callback(self, *args):
        self.args = args
        self.callback_count += 1

        def register(fn):
            self.render = fn
            return fn

        return register


def test_one_callback_supplies_two_cards_from_the_same_preparation(monkeypatch):
    prepared = decode_stockpile_chacay_store({'latest': {'values': {}}})
    seen = []
    sources = []

    def decode(source):
        sources.append(source)
        return prepared

    def map_stockpile(readings):
        seen.append(readings)
        return 'stockpile'

    def map_trend(readings, timeseries):
        seen.append(readings)
        assert timeseries is prepared[1]
        return 'trend'

    monkeypatch.setattr(runtime, 'decode_stockpile_chacay_store', decode)
    monkeypatch.setattr(runtime, 'map_stockpile_chacay_readings', map_stockpile)
    monkeypatch.setattr(runtime, 'map_tendencia_alimentado_readings', map_trend)
    monkeypatch.setattr(runtime, 'build_stockpile_chacay_cards', lambda **parts: parts)

    dash = DashStub()
    runtime.register_stockpile_chacay_callback(dash, tool_key='operations')
    assert dash.callback_count == 1
    assert [output.component_id for output in dash.args[:2]] == [
        dashboard_card_content_id('stockpile_chacay'),
        dashboard_card_content_id('tendencia_alimentado'),
    ]
    assert dash.args[2].component_id == component_kpi_store_id(
        'operations', STOCKPILE_CHACAY.tool_component_key
    )
    raw = {'latest': {'values': {}}}
    assert dash.render(raw) == {'stockpile': 'stockpile', 'tendencia': 'trend'}
    assert sources == [raw]
    assert len(seen) == 2
    assert seen[0] is seen[1] is prepared[0]


def test_each_legacy_card_key_is_preserved():
    assert len(STOCKPILE_CHACAY_PILES) == 4
    assert len(STOCKPILE_CHACAY_ROWS) == 4
    assert len(ALIMENTADO_TRENDS) == 3
