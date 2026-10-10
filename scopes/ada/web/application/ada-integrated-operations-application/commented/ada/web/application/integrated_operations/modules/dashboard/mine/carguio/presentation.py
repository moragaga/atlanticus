# Agrupa las presentaciones en el orden exacto de los tres Output del runtime.
# No altera las tarjetas ni la ubicación de Gestión Carguío Turno.
from __future__ import annotations

from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus

from .carguio_global_turno import build_carguio_global_turno
from .carguio_global_turno.models import CarguioGlobalTurnoState
from .equipos_servicio import build_equipos_servicio
from .equipos_servicio.models import EquiposServicioState
from .gestion_carguio_turno import build_gestion_carguio_turno
from .gestion_carguio_turno.models import GestionCarguioTurnoState


def build_carguio(
    *,
    carguio_global_turno: tuple[CarguioGlobalTurnoState | None, DisplayStatus],
    equipos_servicio: tuple[EquiposServicioState | None, DisplayStatus],
    gestion_carguio_turno: tuple[GestionCarguioTurnoState | None, DisplayStatus],
) -> tuple[Component, Component, Component]:
    return (
        build_carguio_global_turno(*carguio_global_turno),
        build_equipos_servicio(*equipos_servicio),
        build_gestion_carguio_turno(*gestion_carguio_turno),
    )
