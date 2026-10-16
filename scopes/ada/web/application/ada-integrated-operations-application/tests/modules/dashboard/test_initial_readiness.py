import pytest
from dash import Input
from dash.exceptions import PreventUpdate

from ada.web.application.integrated_operations.modules.dashboard.initial_readiness import require_initial_delivery


def test_pending_store_blocks_but_empty_store_renders():
    with pytest.raises(PreventUpdate):
        require_initial_delivery(None)
    require_initial_delivery({'latest': None, 'timeseries': None})


def test_every_operational_area_renders_only_on_its_own_store():
    from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.runtime import register_carguio_callback
    from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.runtime import register_chancado_stmg_callback
    from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.runtime import register_general_mina_callback
    from ada.web.application.integrated_operations.modules.dashboard.mine.transporte.runtime import register_transporte_callback
    from ada.web.application.integrated_operations.modules.dashboard.plant.flotacion.runtime import register_flotacion_callback
    from ada.web.application.integrated_operations.modules.dashboard.plant.molienda.runtime import register_molienda_callback
    from ada.web.application.integrated_operations.modules.dashboard.plant.puerto.runtime import register_puerto_callback
    from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.runtime import register_stockpile_chacay_callback
    from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.runtime import register_transporte_fluidos_callback
    from ada.web.kpis.collector import component_kpi_store_id

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
        app = DashStub()
        register(app, tool_key='integrated_operations')
        inputs = [item for item in app.callback_args if isinstance(item, Input)]
        assert len(inputs) == 1
        assert inputs[0].component_id['type'] == component_kpi_store_id(
            'integrated_operations', inputs[0].component_id['component'],
        )['type']
        with pytest.raises(PreventUpdate):
            app.callback_function(None)
        result = app.callback_function({'latest': None, 'timeseries': None})
        assert result[-1] == 'true'
