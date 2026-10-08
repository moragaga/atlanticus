# Descifra Latest sin inventar ceros ni fallbacks. Una lectura faltante no afecta a las demás.
from __future__ import annotations

from collections.abc import Mapping

from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus, DisplayValue

from .definitions import PRODUCCION_GLOBAL_DEFINITIONS
from .models import ProduccionGlobalMetric, ProduccionGlobalRow, ProduccionGlobalState


# La tabla consume el mismo Store Latest de Chancado-STMG.
def map_produccion_global_store(store_data: object) -> ProduccionGlobalState:
    values, source_status = _latest_values(store_data)
    return ProduccionGlobalState(
        rows=tuple(
            ProduccionGlobalRow(
                key=definition.key,
                label=definition.label,
                real=_metric(values, definition.real_key, source_status),
                plan_acumulado=_metric(values, definition.plan_acumulado_key, source_status),
                proyeccion=_metric(values, definition.proyeccion_key, source_status),
                plan_dia=_metric(values, definition.plan_dia_key, source_status),
                requerido_hora=_metric(values, definition.requerido_hora_key, source_status),
            )
            for definition in PRODUCCION_GLOBAL_DEFINITIONS
        )
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


# Conserva NOT_MAPPED, EMPTY, INVALID y ERROR en cada valor escalar independiente.
def _metric(
    values: Mapping[str, object] | None,
    kpi_key: str,
    source_status: DisplayStatus,
) -> ProduccionGlobalMetric:
    if values is None:
        return ProduccionGlobalMetric(kpi_key, DisplayValue(source_status))
    decoded = decode_kpi_latest_value(values.get(kpi_key), present=kpi_key in values)
    if decoded.state is KpiLatestValueState.OK:
        if decoded.value_kind != 'value' or not isinstance(decoded.value, str):
            display = DisplayValue.invalid()
        elif not decoded.value.strip():
            display = DisplayValue.invalid()
        else:
            display = DisplayValue.ok(decoded.value.strip())
    elif decoded.state is KpiLatestValueState.NOT_MAPPED:
        display = DisplayValue.not_mapped()
    elif decoded.state is KpiLatestValueState.MISSING:
        display = DisplayValue.empty()
    elif decoded.state is KpiLatestValueState.ERROR:
        display = DisplayValue.error()
    else:
        display = DisplayValue.invalid()
    return ProduccionGlobalMetric(kpi_key, display)
