from __future__ import annotations

from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.plant.puerto.decoder import (
    decode_puerto_store,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.puerto.desaladora import (
    VOLUMEN,
    build_desaladora,
    map_desaladora_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.puerto.puerto import (
    FILTRADO_ACCUMULATED,
    SHIPMENT,
    build_puerto,
    map_puerto_readings,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.decoder import (
    decode_transporte_fluidos_store,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.stc import (
    STC_ESPESADOR,
    build_stc,
    map_stc_readings,
)


def _entry(value: object) -> dict[str, object]:
    return {
        'status': 'ok',
        'value_kind': 'value',
        'value': str(value),
        'value_type': 'text',
        'parsed_value': str(value),
    }


def _walk(value):
    if isinstance(value, Component):
        yield value
        yield from _walk(getattr(value, 'children', None))
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)


def _row(root, key: str):
    targets = [
        node for node in _walk(root)
        if getattr(node, 'data-kpi-inspection-key', None) == key
    ]
    assert len(targets) == 1
    target = targets[0]
    assert target.role == 'button' and target.tabIndex == 0
    nodes = list(_walk(target))
    rows = [
        node for node in nodes
        if 'ada-inline-value-row' in (getattr(node, 'className', '') or '').split()
    ]
    assert len(rows) == 1
    label = next(
        node for node in nodes
        if getattr(node, 'className', None) == 'ada-inline-value-row__label'
    )
    units = [
        node for node in nodes
        if getattr(node, 'className', None) == 'ada-inline-value-row__unit'
    ]
    value = next(
        node for node in nodes
        if getattr(node, 'className', None) == 'ada-inline-value-row__value'
    )
    return label.children, [unit.children for unit in units], value.children


def test_stc_thickener_metrics_share_inline_row_and_kpi_inspection():
    values = {
        STC_ESPESADOR.state_key: _entry('Operando'),
        STC_ESPESADOR.feed_key: _entry('Alimentando'),
    }
    for metric in STC_ESPESADOR.metrics:
        values[metric.kpi_key] = _entry('21')
    readings = decode_transporte_fluidos_store({'latest': {'values': values}})
    root = build_stc(map_stc_readings(readings))
    assert [(m.label, m.unit) for m in STC_ESPESADOR.metrics] == [
        ('Altura', '%'),
        ('Torque', '%'),
        ('Flujo', 't/h'),
        ('Sólido', '%'),
    ]
    for metric in STC_ESPESADOR.metrics:
        assert _row(root, metric.kpi_key) == (metric.label, [f'({metric.unit})'], '21')
    for key in (STC_ESPESADOR.state_key, STC_ESPESADOR.feed_key):
        assert len([
            node for node in _walk(root)
            if getattr(node, 'data-kpi-inspection-key', None) == key
        ]) == 1


def test_stc_degraded_metric_preserves_icon_in_inline_row():
    key = STC_ESPESADOR.metrics[0].kpi_key
    readings = decode_transporte_fluidos_store({'latest': {'values': {
        key: {'status': 'error', 'value_kind': 'json', 'value': None,
              'value_type': None, 'parsed_value': None},
    }}})
    root = build_stc(map_stc_readings(readings))
    _, _, value = _row(root, key)
    assert isinstance(value, Component)


def test_puerto_and_desaladora_labels_units_and_existing_inline_rows():
    data = {'latest': {'values': {
        FILTRADO_ACCUMULATED.kpi_key: _entry('120'),
        SHIPMENT.tonnage.kpi_key: _entry('82'),
        SHIPMENT.duration_key: _entry('3600'),
        VOLUMEN.kpi_key: _entry('15'),
    }}}
    readings, histories = decode_puerto_store(data)
    port = build_puerto(map_puerto_readings(readings, histories))
    desal = build_desaladora(map_desaladora_readings(readings, histories))
    assert _row(port, FILTRADO_ACCUMULATED.kpi_key) == (
        'Concentrado Filtrado Día', ['(TMH)'], '120'
    )
    assert _row(port, SHIPMENT.tonnage.kpi_key) == (
        'Tonelaje', ['(TMH)'], '82'
    )
    assert _row(port, SHIPMENT.duration_key) == ('Tiempo', ['(h)'], '>1')
    assert _row(desal, VOLUMEN.kpi_key) == (
        'Impulsión Día', ['(l/s)'], '15'
    )
    assert FILTRADO_ACCUMULATED.kpi_key == 'filtrado_acumulado_dia'
    assert VOLUMEN.kpi_key == 'volumen_real_acc_dia'


def test_puerto_degraded_value_uses_same_inline_row():
    data = {'latest': {'values': {
        FILTRADO_ACCUMULATED.kpi_key: {
            'status': 'error', 'value_kind': 'json', 'value': None,
            'value_type': None, 'parsed_value': None,
        },
    }}}
    readings, histories = decode_puerto_store(data)
    port = build_puerto(map_puerto_readings(readings, histories))
    label, units, value = _row(port, FILTRADO_ACCUMULATED.kpi_key)
    assert label == 'Concentrado Filtrado Día' and units == ['(TMH)']
    assert isinstance(value, Component)
