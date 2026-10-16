from __future__ import annotations

from dash import Input, Output

from ada.web.application.integrated_operations.modules.dashboard.initial_readiness import require_initial_delivery

from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_card_content_id,
    dashboard_component_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import GENERAL_MINA
from ada.web.kpis.collector import KpiLatestValueState, component_kpi_store_id
from ada.web.ui.display_status import DisplayStatus

from .decoder import decode_general_mina_store
from .movimiento_mina import (
    MovimientoMinaContractError,
    MovimientoMinaUnavailableError,
    map_movimiento_mina_readings,
)
from .mp10 import map_mp10_readings
from .perforacion import map_perforacion_readings
from .presentation import build_general_mina
from .remanentes import map_remanentes_readings

_SOURCE_STATUS = {
    KpiLatestValueState.NOT_MAPPED: DisplayStatus.NOT_MAPPED,
    KpiLatestValueState.MISSING: DisplayStatus.EMPTY,
    KpiLatestValueState.ERROR: DisplayStatus.INVALID,
}


def register_general_mina_callback(dash_app, *, tool_key: str) -> None:
    @dash_app.callback(
        Output(dashboard_card_content_id('movimiento_mina'), 'children'),
        Output(dashboard_card_content_id('remanentes'), 'children'),
        Output(dashboard_card_content_id('perforacion'), 'children'),
        Output(dashboard_card_content_id('mp10'), 'children'),
        Output(dashboard_component_id(GENERAL_MINA.key), 'data-ready'),
        Input(component_kpi_store_id(tool_key, GENERAL_MINA.tool_component_key), 'data'),
    )
    def refresh_general_mina(store_data: object):
        require_initial_delivery(store_data)
        readings = decode_general_mina_store(store_data)
        try:
            movimiento = map_movimiento_mina_readings(readings)
        except MovimientoMinaUnavailableError as error:
            movimiento = _SOURCE_STATUS[error.state]
        except MovimientoMinaContractError:
            movimiento = DisplayStatus.INVALID
        rendered = build_general_mina(
            movimiento_mina=movimiento,
            remanentes=map_remanentes_readings(readings),
            perforacion=map_perforacion_readings(readings),
            mp10=map_mp10_readings(readings),
        )
        return (*rendered, 'true')
