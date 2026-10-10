from __future__ import annotations

from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import FLOTACION
from ada.web.application.integrated_operations.modules.dashboard.plant.flotacion.selectiva import (
    ESPESADORES,
    SELECTIVA_INDICATORS,
    build_selectiva,
    map_espesadores_store,
    map_selectiva_indicators_store,
    register_selectiva_callback,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus


def _entry(value: object) -> dict[str, object]:
    return {
        'status': 'ok',
        'value_kind': 'value',
        'value': str(value),
        'value_type': 'text',
        'parsed_value': str(value),
    }


def _store() -> dict[str, object]:
    values = {}
    for number, definition in enumerate(ESPESADORES):
        values[definition.state_kpi_key] = _entry('Operando' if number % 2 else 'Detenido')
        values[definition.feed_kpi_key] = _entry('Alimentando' if number % 2 else 'No Alimentando')
        for metric in definition.metrics:
            values[metric.kpi_key] = _entry('25.6')
    for indicator in SELECTIVA_INDICATORS:
        values[indicator.kpi_key] = _entry('12.5')
    return {'latest': {'values': values}}


def _walk(item):
    if isinstance(item, Component):
        yield item
        yield from _walk(getattr(item, 'children', None))
    elif isinstance(item, (list, tuple)):
        for child in item:
            yield from _walk(child)


def test_current_five_tanks_and_all_legacy_keys():
    assert [item.label for item in ESPESADORES] == ['TK-10', 'TK-12', 'TK-13', 'TK-55', 'TK-56']
    for definition, number in zip(ESPESADORES, ('10', '12', '13', '55', '56'), strict=True):
        assert definition.state_kpi_key == f'tk_{number}_estado_inst'
        assert definition.feed_kpi_key == f'tk_{number}_estado_alimentacion_inst'
        assert [metric.kpi_key for metric in definition.metrics] == [
            f'tk_{number}_altura_inst',
            f'tk_{number}_torque_inst',
            f'tk_{number}_flujo_inst',
            f'tk_{number}_solido_inst',
        ]


def test_old_six_inline_rows_keep_names_units_and_order():
    assert [(item.label, item.kpi_key, item.unit) for item in SELECTIVA_INDICATORS] == [
        ('Conc Colectivo', 'concentrado_colectivo_real_mean_hora', 't/h'),
        ('Ley Mo Env', 'ley_concentrado_mo_real', '%'),
        ('Utilización', 'utilizacion_flotacion_selectiva', '%'),
        ('Recuperación', 'recuperacion_selectiva_mo', '%'),
        ('NaHS', 'nash_real', 'kg/t'),
        ('Producción', 'produccion_selectiva_mo', 'tmf'),
    ]


def test_latest_maps_five_tanks_and_six_indicators():
    tanks = map_espesadores_store(_store())
    indicators = map_selectiva_indicators_store(_store())
    assert len(tanks) == 5
    assert [item.feed.value for item in tanks] == [
        'detenido',
        'operando',
        'detenido',
        'operando',
        'detenido',
    ]
    assert tanks[0].state.value == 'Detenido'
    assert [metric.value.value for metric in tanks[0].metrics] == ['25.6'] * 4
    assert [indicator.value.value for indicator in indicators] == ['12.5'] * 6


def test_unknown_or_missing_feed_never_becomes_detenido():
    store = _store()
    values = store['latest']['values']
    values.pop(ESPESADORES[0].feed_kpi_key)
    values[ESPESADORES[1].feed_kpi_key] = {
        'status': 'missing',
        'value_kind': None,
        'value': None,
        'value_type': None,
        'parsed_value': None,
    }
    values[ESPESADORES[2].feed_kpi_key] = {
        'status': 'error',
        'value_kind': 'json',
        'value': None,
        'value_type': None,
        'parsed_value': None,
    }
    values[ESPESADORES[3].feed_kpi_key] = _entry('unrecognized')
    values[ESPESADORES[4].feed_kpi_key] = _entry(0)
    tanks = map_espesadores_store(store)
    assert [item.feed.status for item in tanks] == [
        DisplayStatus.NOT_MAPPED,
        DisplayStatus.EMPTY,
        DisplayStatus.ERROR,
        DisplayStatus.INVALID,
        DisplayStatus.INVALID,
    ]
    assert all(item.feed.value is None for item in tanks)


def test_tanks_and_indicators_keep_independent_degraded_statuses():
    store = _store()
    values = store['latest']['values']
    values[ESPESADORES[2].metrics[1].kpi_key] = {
        'status': 'error',
        'value_kind': 'json',
        'value': None,
        'value_type': None,
        'parsed_value': None,
    }
    values.pop(SELECTIVA_INDICATORS[0].kpi_key)
    values[SELECTIVA_INDICATORS[1].kpi_key] = {
        'status': 'missing',
        'value_kind': None,
        'value': None,
        'value_type': None,
        'parsed_value': None,
    }
    tanks = map_espesadores_store(store)
    indicators = map_selectiva_indicators_store(store)
    assert tanks[2].metrics[1].value.status is DisplayStatus.ERROR
    assert tanks[2].metrics[0].value.status is DisplayStatus.OK
    assert indicators[0].value.status is DisplayStatus.NOT_MAPPED
    assert indicators[1].value.status is DisplayStatus.EMPTY
    assert indicators[2].value.status is DisplayStatus.OK


def test_missing_delivery_and_invalid_latest_do_not_crash():
    tanks = map_espesadores_store({'latest': {'values': {}}})
    indicators = map_selectiva_indicators_store({'latest': {'values': {}}})
    assert all(item.feed.status is DisplayStatus.NOT_MAPPED for item in tanks)
    assert all(item.value.status is DisplayStatus.NOT_MAPPED for item in indicators)
    assert all(item.feed.status is DisplayStatus.INVALID for item in map_espesadores_store(None))
    assert all(
        item.value.status is DisplayStatus.INVALID for item in map_selectiva_indicators_store(None)
    )


def test_each_selectiva_key_remains_independently_inspectable():
    root = build_selectiva(
        map_espesadores_store(_store()), map_selectiva_indicators_store(_store())
    )
    nodes = [node for node in _walk(root) if getattr(node, 'data-kpi-inspection-key', None)]
    keys = [getattr(node, 'data-kpi-inspection-key') for node in nodes]
    expected = set()
    for definition in ESPESADORES:
        expected.update((definition.state_kpi_key, definition.feed_kpi_key))
        expected.update(metric.kpi_key for metric in definition.metrics)
    expected.update(item.kpi_key for item in SELECTIVA_INDICATORS)
    assert set(keys) == expected
    assert len(keys) == len(expected)
    assert all(node.role == 'button' and node.tabIndex == 0 for node in nodes)
    images = [
        node
        for node in _walk(root)
        if getattr(node, 'src', '').endswith(('/operando.svg', '/detenido.svg'))
    ]
    assert len(images) == 5
    assert all('/equipment/espesador/' in node.src for node in images)
    circles = [
        node
        for node in _walk(root)
        if 'ada-io-selectiva__feed-circle--' in (getattr(node, 'className', '') or '')
    ]
    assert len(circles) == 5


class DashStub:
    def __init__(self):
        self.args = None
        self.render = None

    def callback(self, *args):
        self.args = args

        def register(fn):
            self.render = fn
            return fn

        return register


def test_selectiva_callback_reuses_existing_flotacion_store():
    dash_app = DashStub()
    register_selectiva_callback(dash_app, tool_key='integrated_operations')
    assert dash_app.args[0].component_id == dashboard_card_content_id('selectiva')
    assert dash_app.args[1].component_id == component_kpi_store_id(
        'integrated_operations', FLOTACION.tool_component_key
    )
    assert isinstance(dash_app.render(_store()), Component)
