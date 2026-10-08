# Los tres KPI se decodifican independientemente y solo se reconocen estados explícitos.
from __future__ import annotations

from collections.abc import Mapping, Sequence

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .models import EquiposChDefinition, EquiposChReading

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
        )
    ]
    if len(keys) != len(set(keys)):
        raise ValueError('Equipos CH KPI keys must be globally distinct')

    values, source_status = _latest_values(store_data)
    return tuple(
        EquiposChReading(
            definition=definition,
            state=_state(values, definition.state_kpi_key, source_status),
            throughput=_throughput(values, definition.throughput_kpi_key, source_status),
            atollo=_atollo(values, definition, source_status),
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
