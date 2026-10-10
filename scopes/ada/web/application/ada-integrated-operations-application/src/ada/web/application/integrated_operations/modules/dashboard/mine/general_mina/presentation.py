from __future__ import annotations

from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus

from .movimiento_mina import build_movimiento_mina, build_movimiento_mina_unavailable
from .movimiento_mina.models import MovimientoMinaState
from .mp10 import build_mp10
from .mp10.models import MP10State
from .perforacion import build_perforacion
from .perforacion.models import PerforacionState
from .remanentes import build_remanentes
from .remanentes.models import RemanentesState


def build_general_mina(
    *,
    movimiento_mina: MovimientoMinaState | DisplayStatus,
    remanentes: RemanentesState,
    perforacion: PerforacionState,
    mp10: MP10State,
) -> tuple[Component, Component, Component, Component]:
    movimiento = (
        build_movimiento_mina_unavailable(movimiento_mina)
        if isinstance(movimiento_mina, DisplayStatus)
        else build_movimiento_mina(movimiento_mina)
    )
    return (
        movimiento,
        build_remanentes(remanentes),
        build_perforacion(perforacion),
        build_mp10(mp10),
    )
