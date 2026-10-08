# Adapta el KPI JSON agrupado de Gestión Carguío • Turno sin inferir spans ni recalcular datos.
from __future__ import annotations

from collections.abc import Mapping

from ada.web.application.integrated_operations.modules.dashboard.data_state import (
    DashboardDataState,
    map_dashboard_data_state,
)
from ada.web.kpis.collector import KpiLatestValueState, decode_kpi_latest_value
from ada.web.ui.display_status import DisplayStatus

from .definitions import GESTION_CARGUIO_TURNO_KPI_KEY
from .models import (
    GestionCarguioTurnoRow,
    GestionCarguioTurnoSection,
    GestionCarguioTurnoState,
)

_SOURCE_STATUS = {
    KpiLatestValueState.NOT_MAPPED: DisplayStatus.NOT_MAPPED,
    KpiLatestValueState.MISSING: DisplayStatus.EMPTY,
    KpiLatestValueState.INVALID: DisplayStatus.INVALID,
    KpiLatestValueState.ERROR: DisplayStatus.INVALID,
}


def map_gestion_carguio_turno_store(
    store_data: object,
) -> tuple[GestionCarguioTurnoState | None, DisplayStatus]:
    values, source_status = _latest_values(store_data)
    if values is None:
        return None, source_status

    decoded = decode_kpi_latest_value(
        values.get(GESTION_CARGUIO_TURNO_KPI_KEY),
        present=GESTION_CARGUIO_TURNO_KPI_KEY in values,
    )
    if decoded.state is not KpiLatestValueState.OK:
        return None, _SOURCE_STATUS[decoded.state]
    if decoded.value_kind != 'json' or not isinstance(decoded.value, Mapping):
        return None, DisplayStatus.INVALID

    try:
        return _map_payload(decoded.value), DisplayStatus.OK
    except (TypeError, ValueError):
        return None, DisplayStatus.INVALID


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


def _map_payload(payload: Mapping[str, object]) -> GestionCarguioTurnoState:
    if 'data_state' not in payload:
        raise ValueError('Gestion Carguio Turno data_state is required')
    data_state = map_dashboard_data_state(payload['data_state'])

    # ERROR puede omitir el detalle porque no existe contenido útil que presentar.
    if data_state is DashboardDataState.ERROR:
        return GestionCarguioTurnoState(sections=(), data_state=data_state)

    sections = payload.get('sections')
    if not isinstance(sections, list):
        raise ValueError('Gestion Carguio Turno sections must be a JSON array')

    # Backend define las categorías, su orden y el orden de sus equipos.
    return GestionCarguioTurnoState(
        sections=tuple(_map_section(item) for item in sections),
        data_state=data_state,
    )


def _map_section(value: object) -> GestionCarguioTurnoSection:
    if not isinstance(value, Mapping):
        raise ValueError('Gestion Carguio Turno section must be an object')

    label = _require_value(value, 'label')
    if not isinstance(label, str) or not label.strip():
        raise ValueError('Gestion Carguio Turno section label must be non-empty')

    rows = value.get('rows')
    if not isinstance(rows, list):
        raise ValueError('Gestion Carguio Turno section rows must be a JSON array')

    return GestionCarguioTurnoSection(
        label=label,
        rows=tuple(_map_row(item) for item in rows),
    )


def _map_row(value: object) -> GestionCarguioTurnoRow:
    if not isinstance(value, Mapping):
        raise ValueError('Gestion Carguio Turno row must be an object')

    equipo = _require_value(value, 'equipo')
    if not isinstance(equipo, str) or not equipo.strip():
        raise ValueError('Gestion Carguio Turno equipo must be a non-empty string')

    # Las celdas son valores opacos; Web sólo preserva lo recibido.
    return GestionCarguioTurnoRow(
        equipo=equipo,
        fase=_require_scalar_or_null(value, 'fase'),
        uebd_pct=_require_scalar_or_null(value, 'uebd_pct'),
        disponibilidad_fisica_pct=_require_scalar_or_null(
            value,
            'disponibilidad_fisica_pct',
        ),
        rendimiento_efectivo_tph=_require_scalar_or_null(
            value,
            'rendimiento_efectivo_tph',
        ),
        cola_pala_min=_require_scalar_or_null(value, 'cola_pala_min'),
        estado=_require_scalar_or_null(value, 'estado'),
        razon=_require_scalar_or_null(value, 'razon'),
    )


def _require_scalar_or_null(
    container: Mapping[str, object],
    key: str,
) -> str | int | float | bool | None:
    value = _require_value(container, key)
    if value is not None and not isinstance(value, str | int | float | bool):
        raise TypeError(f'Gestion Carguio Turno field must be scalar or null: {key}')
    return value


def _require_value(container: Mapping[str, object], key: str) -> object:
    if key not in container:
        raise ValueError(f'Gestion Carguio Turno field is required: {key}')
    return container[key]
