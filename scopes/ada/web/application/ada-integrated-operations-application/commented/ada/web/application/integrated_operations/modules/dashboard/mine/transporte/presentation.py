# Une las dos presentaciones sin modificar su contenido ni el orden de Output.
from __future__ import annotations

from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus

from .numero_operativo_turno import build_numero_operativo_turno
from .numero_operativo_turno.models import NumeroOperativoTurnoState
from .transporte_global_turno import build_transporte_global_turno
from .transporte_global_turno.models import TransporteGlobalTurnoState


def build_transporte(
    *,
    transporte_global_turno: tuple[TransporteGlobalTurnoState | None, DisplayStatus],
    numero_operativo_turno: tuple[NumeroOperativoTurnoState | None, DisplayStatus],
) -> tuple[Component, Component]:
    return (
        build_transporte_global_turno(*transporte_global_turno),
        build_numero_operativo_turno(*numero_operativo_turno),
    )
