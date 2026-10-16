import pytest
from dash import Input, State
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
            require_initial_delivery({'latest': None, 'timeseries': None}, revision, 'normal')


def test_completed_latest_unblocks_all_destinations_even_without_payload():
    require_initial_delivery(None, LATEST_READY, 'normal')
    require_initial_delivery({'latest': None, 'timeseries': None}, LATEST_READY, 'normal')
    require_initial_delivery({'latest': {'manifest': {}, 'values': {}}}, LATEST_READY, 'normal')


def test_read_complete_with_no_document_or_error_is_terminal():
    for state in ('empty', 'error'):
        require_initial_delivery(None, {'latest': None, 'initial_latest_state': state}, 'normal')
    with pytest.raises(PreventUpdate):
        require_initial_delivery(None, {'latest': {'revision': 'latest-r1'}}, 'normal')


def test_all_dashboard_areas_use_collector_revision_as_input():
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
    from ada.web.time_status.runtime import time_status_runtime_host_id

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
        registered = dash.callback_args[-3:]
        assert [type(item).__name__ for item in registered] == ['Input', 'Input', 'State']
        assert registered[0].component_id == DEFAULT_KPI_COLLECTOR_REVISION_STORE_ID
        assert registered[1].component_id == 'ada-generic-application'
        assert isinstance(registered[2], State)
        assert any(
            getattr(item, 'component_id', None) == DEFAULT_KPI_COLLECTOR_REVISION_STORE_ID
            and getattr(item, 'component_property', None) == 'data'
            for item in dash.callback_args
        )
        assert any(
            isinstance(item, Input)
            and getattr(item, "component_id", None) == DEFAULT_KPI_COLLECTOR_REVISION_STORE_ID
            for item in dash.callback_args
        )
        with pytest.raises(PreventUpdate):
            dash.callback_function(None, 'normal', {'latest': None})
        rendered = dash.callback_function(LATEST_READY, 'normal', {'latest': None})
        assert rendered[-1] == 'true'
        authoring = dash.callback_function(None, 'authoring', {'latest': None})
        assert authoring[-1] == 'true'


def test_revision_is_required_only_in_normal_mode():
    with pytest.raises(PreventUpdate):
        require_initial_delivery(None, None, 'normal')
    require_initial_delivery(None, None, 'authoring')
