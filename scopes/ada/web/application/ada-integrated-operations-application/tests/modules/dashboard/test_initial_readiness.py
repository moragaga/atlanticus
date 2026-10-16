import pytest
from dash.exceptions import PreventUpdate

from ada.web.application.integrated_operations.modules.dashboard.initial_readiness import (
    require_initial_delivery,
)

LATEST_READY = {
    'latest': {'revision': 'latest-r1'},
    'timeseries': None,
    'initial_latest_state': 'ready',
}


def test_no_revision_defers_even_in_local_mode(monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    for revision in (None, {}, {'latest': None}, {'latest': {}}, {'latest': {'revision': ''}}):
        with pytest.raises(PreventUpdate):
            require_initial_delivery({'latest': None, 'timeseries': None}, revision)


def test_completed_latest_unblocks_all_destinations_even_without_payload():
    require_initial_delivery(None, LATEST_READY)
    require_initial_delivery({'latest': None, 'timeseries': None}, LATEST_READY)
    require_initial_delivery({'latest': {'manifest': {}, 'values': {}}}, LATEST_READY)


def test_read_complete_with_no_document_or_error_is_terminal():
    for state in ('empty', 'error'):
        require_initial_delivery(None, {'latest': None, 'initial_latest_state': state})
    with pytest.raises(PreventUpdate):
        require_initial_delivery(None, {'latest': {'revision': 'latest-r1'}})


def test_all_dashboard_area_callbacks_wait_for_collector_revision():
    from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.runtime import register_carguio_callback
    from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.runtime import register_chancado_stmg_callback
    from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.runtime import register_general_mina_callback
    from ada.web.application.integrated_operations.modules.dashboard.mine.transporte.runtime import register_transporte_callback
    from ada.web.application.integrated_operations.modules.dashboard.plant.flotacion.runtime import register_flotacion_callback
    from ada.web.application.integrated_operations.modules.dashboard.plant.molienda.runtime import register_molienda_callback
    from ada.web.application.integrated_operations.modules.dashboard.plant.puerto.runtime import register_puerto_callback
    from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.runtime import register_stockpile_chacay_callback
    from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.runtime import register_transporte_fluidos_callback
    from ada.web.kpis.collector.presentation import DEFAULT_KPI_COLLECTOR_REVISION_STORE_ID

    class DashStub:
        callback_function = None
        callback_args = None

        def callback(self, *args):
            self.callback_args = args
            def register(function):
                self.callback_function = function
                return function
            return register

    registrations = (
        register_general_mina_callback, register_carguio_callback,
        register_transporte_callback, register_chancado_stmg_callback,
        register_stockpile_chacay_callback, register_molienda_callback,
        register_flotacion_callback, register_transporte_fluidos_callback,
        register_puerto_callback,
    )
    for register in registrations:
        dash = DashStub()
        register(dash, tool_key='integrated_operations')
        assert any(
            getattr(item, 'component_id', None) == DEFAULT_KPI_COLLECTOR_REVISION_STORE_ID
            and getattr(item, 'component_property', None) == 'data'
            for item in dash.callback_args
        )
        with pytest.raises(PreventUpdate):
            dash.callback_function({'latest': None, 'timeseries': None}, None)
        result = dash.callback_function({'latest': None, 'timeseries': None}, LATEST_READY)
        assert result[-1] == 'true'
