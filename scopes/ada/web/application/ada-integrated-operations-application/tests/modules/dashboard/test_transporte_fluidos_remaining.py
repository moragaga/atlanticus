from __future__ import annotations

from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    TRANSPORTE_FLUIDOS,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos import (
    register_transporte_fluidos_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.decoder import (
    decode_transporte_fluidos_store,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.sta import (
    STA_INDICATORS,
    build_sta,
    map_sta_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.stc import (
    STC_ESPESADOR,
    STC_INDICATORS,
    STC_LEVELS,
    build_stc,
    map_stc_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.tranque import (
    TRANQUE_INDICATORS,
    build_tranque,
    map_tranque_readings,
)
from ada.web.kpis.collector import component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus


def _entry(value):
    return {'status': 'ok', 'value_kind': 'value', 'value': str(value),
            'value_type': 'text', 'parsed_value': str(value)}


def _store():
    data = {}
    definitions = (*STC_INDICATORS, *TRANQUE_INDICATORS, *STA_INDICATORS, *STC_ESPESADOR.metrics)
    for definition in definitions:
        data[definition.kpi_key] = _entry('12.5')
    data[STC_ESPESADOR.state_key] = _entry('operando')
    data[STC_ESPESADOR.feed_key] = _entry('alimentando')
    for definition in STC_LEVELS:
        data[definition.level_key] = _entry('55')
        data[definition.state_key] = _entry('operando')
        data[definition.color_key] = _entry('2')
    return {'latest': {'values': data}}


def _walk(item):
    if isinstance(item, Component):
        yield item
        yield from _walk(getattr(item, 'children', None))
    elif isinstance(item, (list, tuple)):
        for child in item:
            yield from _walk(child)


def test_old_indicator_contracts_and_order():
    assert [item.kpi_key for item in STC_INDICATORS] == [
        'concentrado_entregado_puerto_real_mean_hora',
        'solido_puerto_real_mean_hora',
        'malla_100_real',
    ]
    assert [item.kpi_key for item in TRANQUE_INDICATORS] == [
        'produccion_arenas_real_acc_dia',
        'cp_descarga_real_mean_hora',
    ]
    assert [item.kpi_key for item in STA_INDICATORS] == [
        'make_up_real_mean_hora',
        'flujo_r2_real_mean_hora',
        'captacion_agua_real_mean_hora',
        'disponibilidad_bombas_tk52_real',
        'batimetria_real_mean_hora',
        'nivel_piscina_norte_real_mean_hora',
        'nivel_piscina_sur_real_mean_hora',
        'nivel_piscina_norte_norte_real_mean_hora',
    ]


def test_current_stc_thickener_and_level_keys():
    assert STC_ESPESADOR.label == 'TK-711'
    assert [item.label for item in STC_ESPESADOR.metrics] == ['Altura', 'Torque', 'Flujo', 'Sólido']
    assert [item.level_key for item in STC_LEVELS] == ['nivel_tk_020_inst', 'nivel_tk_021_inst']
    data = map_stc_readings(decode_transporte_fluidos_store(_store()))
    assert data.espesador.feed.value == 'operando'
    assert data.levels[0].level.value == '55'
    assert data.levels[0].tone == 'warning'


def test_unmapped_feed_and_levels_are_not_faked():
    data = _store()
    values = data['latest']['values']
    del values[STC_ESPESADOR.feed_key]
    del values[STC_LEVELS[0].state_key]
    values[STC_LEVELS[1].level_key] = {
        'status': 'error', 'value_kind': 'json', 'value': None,
        'value_type': None, 'parsed_value': None,
    }
    result = map_stc_readings(decode_transporte_fluidos_store(data))
    assert result.espesador.feed.status is DisplayStatus.NOT_MAPPED
    assert result.levels[0].state.status is DisplayStatus.NOT_MAPPED
    assert result.levels[1].level.status is DisplayStatus.ERROR


def test_invalid_feed_does_not_become_detenido():
    data = _store()
    data['latest']['values'][STC_ESPESADOR.feed_key] = _entry('unknown')
    assert map_stc_readings(decode_transporte_fluidos_store(data)).espesador.feed.status is DisplayStatus.INVALID


def test_metric_status_independence():
    data = _store()
    del data['latest']['values'][STA_INDICATORS[0].kpi_key]
    data['latest']['values'][TRANQUE_INDICATORS[1].kpi_key] = {
        'status': 'missing', 'value_kind': None, 'value': None,
        'value_type': None, 'parsed_value': None,
    }
    readings = decode_transporte_fluidos_store(data)
    assert map_sta_readings(readings)[0].value.status is DisplayStatus.NOT_MAPPED
    assert map_tranque_readings(readings)[1].value.status is DisplayStatus.EMPTY
    assert map_stc_readings(readings).indicators[0].value.status is DisplayStatus.OK


def _inspection_keys(root):
    return [
        getattr(node, 'data-kpi-inspection-key')
        for node in _walk(root)
        if getattr(node, 'data-kpi-inspection-key', None)
    ]


def test_inspection_of_all_current_keys():
    readings = decode_transporte_fluidos_store(_store())
    keys = _inspection_keys(build_stc(map_stc_readings(readings)))
    expected = {item.kpi_key for item in (*STC_INDICATORS, *STC_ESPESADOR.metrics)}
    expected.update((STC_ESPESADOR.state_key, STC_ESPESADOR.feed_key))
    expected.update(item.level_key for item in STC_LEVELS)
    assert set(keys) == expected
    assert len(keys) == len(set(keys))
    for definitions, mapping, builder in (
        (TRANQUE_INDICATORS, map_tranque_readings, build_tranque),
        (STA_INDICATORS, map_sta_readings, build_sta),
    ):
        keys = _inspection_keys(builder(mapping(readings)))
        assert keys == [item.kpi_key for item in definitions]


class DashStub:
    def __init__(self):
        self.args = []
        self.renderer = None

    def callback(self, *args):
        self.args = args
        def register(fn):
            self.renderer = fn
            return fn
        return register


def test_callbacks_read_shared_fluid_store_without_new_collector():
    app = DashStub()
    register_transporte_fluidos_callback(app, tool_key='operations')
    assert [item.component_id for item in app.args[:4]] == [
        dashboard_card_content_id(key) for key in ('str', 'stc', 'tranque', 'sta')
    ]
    assert app.args[4].component_id == component_kpi_store_id(
        'operations', TRANSPORTE_FLUIDOS.tool_component_key
    )
    assert len(app.renderer(_store())) == 4
