from ada.web.application.integrated_operations.modules.dashboard.ids import (
    dashboard_component_id,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import (
    CARGUIO, CHANCADO_STMG, GENERAL_MINA, TRANSPORTE,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.runtime import register_carguio_callback
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.runtime import register_chancado_stmg_callback
from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.runtime import register_general_mina_callback
from ada.web.application.integrated_operations.modules.dashboard.mine.transporte.runtime import register_transporte_callback
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    FLOTACION, MOLIENDA, PUERTO, STOCKPILE_CHACAY, TRANSPORTE_FLUIDOS,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.flotacion.runtime import register_flotacion_callback
from ada.web.application.integrated_operations.modules.dashboard.plant.molienda.runtime import register_molienda_callback
from ada.web.application.integrated_operations.modules.dashboard.plant.puerto.runtime import register_puerto_callback
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.runtime import register_stockpile_chacay_callback
from ada.web.application.integrated_operations.modules.dashboard.plant.transporte_fluidos.runtime import register_transporte_fluidos_callback


class DashStub:
    def __init__(self):
        self.outputs = None

    def callback(self, *args):
        self.outputs = args
        return lambda fn: fn


def test_every_area_callback_emits_first_render_signal():
    entries = (
        (GENERAL_MINA, register_general_mina_callback),
        (CARGUIO, register_carguio_callback),
        (TRANSPORTE, register_transporte_callback),
        (CHANCADO_STMG, register_chancado_stmg_callback),
        (STOCKPILE_CHACAY, register_stockpile_chacay_callback),
        (MOLIENDA, register_molienda_callback),
        (FLOTACION, register_flotacion_callback),
        (TRANSPORTE_FLUIDOS, register_transporte_fluidos_callback),
        (PUERTO, register_puerto_callback),
    )
    for binding, register in entries:
        dash = DashStub()
        register(dash, tool_key='integrated_operations')
        output = dash.outputs[-2]
        assert output.component_id == dashboard_component_id(binding.key)
        assert output.component_property == 'data-ready'
