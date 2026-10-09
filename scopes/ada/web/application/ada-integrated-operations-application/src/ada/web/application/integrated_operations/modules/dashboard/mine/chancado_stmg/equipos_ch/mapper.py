from __future__ import annotations

from collections.abc import Mapping, Sequence

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    map_dashboard_value_status,
)
from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.feeder import FeederColor, FeederValues

from .models import EquiposChDefinition, EquiposChReading, FeederKpiDefinition

_CHANCADOR_STATES = frozenset({'operando', 'detenido', 'mantencion'})


def map_equipos_ch_store(
    store_data: object,
    definitions: Sequence[EquiposChDefinition],
) -> tuple[EquiposChReading, ...]:
    if not isinstance(definitions, Sequence) or not all(
        isinstance(item, EquiposChDefinition) for item in definitions
    ):
        raise TypeError('definitions must be a sequence of EquiposChDefinition')
    keys = [
        key
        for definition in definitions
        for key in (
            definition.state_kpi_key,
            definition.throughput_kpi_key,
            definition.atollo_kpi_key,
            definition.rendimiento_kpi_key,
            definition.min_atollo_kpi_key,
            definition.min_poste_kpi_key,
            definition.rendimiento_color_kpi_key,
            definition.min_atollo_color_kpi_key,
            definition.min_poste_color_kpi_key,
        )
    ]
    keys = [key for key in keys if key is not None]
    if len(keys) != len(set(keys)):
        raise ValueError('Equipos CH KPI keys must be globally distinct')

    values, source_status = _latest_values(store_data)
    return tuple(
        EquiposChReading(
            definition=definition,
            state=_state(values, definition.state_kpi_key, source_status),
            throughput=_throughput(values, definition.throughput_kpi_key, source_status),
            atollo=_atollo(values, definition, source_status),
            rendimiento=_value(values, definition.rendimiento_kpi_key, source_status),
            min_atollo=_value(values, definition.min_atollo_kpi_key, source_status),
            min_poste=_value(values, definition.min_poste_kpi_key, source_status),
            rendimiento_color=_color(values, definition.rendimiento_color_kpi_key, source_status),
            min_atollo_color=_color(values, definition.min_atollo_color_kpi_key, source_status),
            min_poste_color=_color(values, definition.min_poste_color_kpi_key, source_status),
        )
        for definition in definitions
    )


def _latest_values(
    store_data: object,
) -> tuple[Mapping[str, object] | None, DisplayStatus]:
    if not isinstance(store_data, Mapping):
        return None, DisplayStatus.INVALID
    latest = store_data.get('latest')
    if latest is None:
        return None, DisplayStatus.NOT_MAPPED
    if not isinstance(latest, Mapping):
        return None, DisplayStatus.INVALID
    values = latest.get('values')
    if not isinstance(values, Mapping):
        return None, DisplayStatus.INVALID
    return values, DisplayStatus.OK


def _value(
    values: Mapping[str, object] | None,
    key: str,
    source_status: DisplayStatus,
) -> DisplayValue:
    if values is None:
        return DisplayValue(source_status)
    decoded = decode_kpi_latest_value(values.get(key), present=key in values)
    if decoded.state is KpiLatestValueState.NOT_MAPPED:
        return DisplayValue.not_mapped()
    if decoded.state is KpiLatestValueState.MISSING:
        return DisplayValue.empty()
    if decoded.state is KpiLatestValueState.ERROR:
        return DisplayValue.error()
    if decoded.state is not KpiLatestValueState.OK:
        return DisplayValue.invalid()
    if decoded.value_kind != 'value' or not isinstance(decoded.value, str):
        return DisplayValue.invalid()
    normalized = decoded.value.strip()
    if not normalized:
        return DisplayValue.invalid()
    return DisplayValue.ok(normalized)


def _state(
    values: Mapping[str, object] | None,
    key: str,
    source_status: DisplayStatus,
) -> DisplayValue:
    result = _value(values, key, source_status)
    if result.status is DisplayStatus.OK:
        normalized = result.value.lower()
        return DisplayValue.ok(normalized) if normalized in _CHANCADOR_STATES else DisplayValue.invalid()
    return result


def _throughput(
    values: Mapping[str, object] | None,
    key: str,
    source_status: DisplayStatus,
) -> DisplayValue:
    return _value(values, key, source_status)


def _atollo(
    values: Mapping[str, object] | None,
    definition: EquiposChDefinition,
    source_status: DisplayStatus,
) -> DisplayValue:
    result = _value(values, definition.atollo_kpi_key, source_status)
    if result.status is not DisplayStatus.OK:
        return result
    token = result.value.lower()
    if token == definition.atollo_active_value.strip().lower():
        return DisplayValue.ok(True)
    if token == definition.atollo_inactive_value.strip().lower():
        return DisplayValue.ok(False)
    return DisplayValue.invalid()


def _color(
    values: Mapping[str, object] | None,
    key: str | None,
    source_status: DisplayStatus,
) -> DisplayValue | None:
    if key is None:
        return None
    result = _value(values, key, source_status)
    if result.status is not DisplayStatus.OK:
        return result
    try:
        return DisplayValue.ok(map_dashboard_value_status(result.value))
    except ValueError:
        return DisplayValue.invalid()


_FEEDER_COLOR_CODES = {
    '0': FeederColor.NEUTRAL,
    '1': FeederColor.DANGER,
    '2': FeederColor.WARNING,
}


def map_feeders_store(
    store_data: object,
    definitions: Sequence[FeederKpiDefinition],
) -> tuple[FeederValues, ...]:
    if not isinstance(definitions, Sequence) or not all(
        isinstance(item, FeederKpiDefinition) for item in definitions
    ):
        raise TypeError('definitions must be a sequence of FeederKpiDefinition')
    keys = [key for item in definitions for key in (item.percent_kpi_key, item.color_kpi_key) if key]
    if len(set(keys)) != len(keys):
        raise ValueError('Feeder KPI keys must be globally distinct')
    values, status = _latest_values(store_data)
    return tuple(
        FeederValues(
            percent=_feeder_percent(values, definition.percent_kpi_key, status),
            color=(
                _feeder_color(values, definition.color_kpi_key, status)
                if definition.color_kpi_key is not None else None
            ),
        )
        for definition in definitions
    )


def _feeder_read(
    values: Mapping[str, object] | None,
    key: str,
    status: DisplayStatus,
) -> DisplayValue:
    if values is None:
        return DisplayValue(status)
    decoded = decode_kpi_latest_value(values.get(key), present=key in values)
    if decoded.state is KpiLatestValueState.NOT_MAPPED:
        return DisplayValue.not_mapped()
    if decoded.state is KpiLatestValueState.MISSING:
        return DisplayValue.empty()
    if decoded.state is KpiLatestValueState.ERROR:
        return DisplayValue.error()
    if decoded.state is not KpiLatestValueState.OK:
        return DisplayValue.invalid()
    if decoded.value_kind != 'value' or isinstance(decoded.value, bool):
        return DisplayValue.invalid()
    if type(decoded.value) is int:
        return DisplayValue.ok(decoded.value)
    if not isinstance(decoded.value, str):
        return DisplayValue.invalid()
    text = decoded.value.strip()
    return DisplayValue.ok(text) if text else DisplayValue.invalid()


def _feeder_percent(
    values: Mapping[str, object] | None,
    key: str,
    status: DisplayStatus,
) -> DisplayValue:
    reading = _feeder_read(values, key, status)
    if reading.status is not DisplayStatus.OK:
        return reading
    text = reading.value
    if type(text) is int:
        return DisplayValue.ok(text) if text >= 0 else DisplayValue.invalid()
    if not text.isascii() or not text.isdecimal():
        return DisplayValue.invalid()
    try:
        return DisplayValue.ok(int(text))
    except ValueError:
        return DisplayValue.invalid()


def _feeder_color(
    values: Mapping[str, object] | None,
    key: str,
    status: DisplayStatus,
) -> DisplayValue:
    reading = _feeder_read(values, key, status)
    if reading.status is not DisplayStatus.OK:
        return reading
    color = _FEEDER_COLOR_CODES.get(str(reading.value))
    return DisplayValue.ok(color) if color is not None else DisplayValue.invalid()
