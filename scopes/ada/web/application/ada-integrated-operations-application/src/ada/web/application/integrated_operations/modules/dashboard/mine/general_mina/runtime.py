from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import GENERAL_MINA
from ada.web.kpis.collector import KpiLatestValueState, component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus

from .movimiento_mina import (
    MovimientoMinaContractError,
    MovimientoMinaUnavailableError,
    build_movimiento_mina,
    build_movimiento_mina_unavailable,
    map_movimiento_mina_store,
)
from .remanentes import build_remanentes, map_remanentes_store

_SOURCE_STATUS = {
    KpiLatestValueState.NOT_MAPPED: DisplayStatus.NOT_MAPPED,
    KpiLatestValueState.MISSING: DisplayStatus.EMPTY,
    KpiLatestValueState.ERROR: DisplayStatus.ERROR,
}


def register_general_mina_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('movimiento_mina'), 'children'),
        Output(dashboard_card_content_id('remanentes'), 'children'),
        Input(component_kpi_store_id(tool_key, GENERAL_MINA.tool_component_key), 'data'),
    )
    def refresh_general_mina(store_data: object):
        return (
            _render_movimiento_mina(store_data),
            build_remanentes(map_remanentes_store(store_data)),
        )


def _render_movimiento_mina(store_data: object):
    try:
        state = map_movimiento_mina_store(store_data)
    except MovimientoMinaUnavailableError as error:
        return build_movimiento_mina_unavailable(_SOURCE_STATUS[error.state])
    except MovimientoMinaContractError:
        return build_movimiento_mina_unavailable(DisplayStatus.INVALID)
    return build_movimiento_mina(state)
