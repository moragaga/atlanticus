from ada.web.application.integrated_operations.modules.dashboard.context import (
    DASHBOARD_CONTEXT_SERVICE_KEY,
    DashboardContext,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.runtime import (
    register_carguio_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.chancado_stmg.runtime import (
    register_chancado_stmg_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.runtime import (
    register_general_mina_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.module import (
    MINE_ASSET_LAYER,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.transporte.runtime import (
    register_transporte_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.module import (
    PLANT_ASSET_LAYER,
)
# Único registro nuevo en la composición general del Dashboard.
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.runtime import (
    register_stockpile_chacay_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.stockpile_chacay.tendencia_alimentado import (
    register_tendencia_alimentado_callback,
)
from ada.web.operational_render_binding import OperationalRenderBinding
from ada.web.ui.card_display import ADA_CARD_DISPLAY_ASSET_LAYER
from ada.web.ui.equipment_image import ADA_EQUIPMENT_IMAGE_ASSET_LAYER
from ada.web.ui.feeder import ADA_FEEDER_ASSET_LAYER
from ada.web.ui.inline_row import ADA_INLINE_ROW_ASSET_LAYER
from ada.web.ui.stockpile import ADA_STOCKPILE_ASSET_LAYER
from ada.web.ui.time_series import ADA_TIME_SERIES_ASSET_LAYER
from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

DASHBOARD_ASSET_LAYER = AssetLayer(
    name='ada_integrated_operations_dashboard',
    load_order=9000,
    package='ada.web.application.integrated_operations.modules.dashboard',
)

_DASHBOARD_PAGE_PACKAGE = 'ada.web.application.integrated_operations.modules.dashboard.pages'


def create_dashboard_module(binding: OperationalRenderBinding | None) -> WebModule:
    if binding is not None and not isinstance(binding, OperationalRenderBinding):
        raise TypeError('Dashboard binding must be OperationalRenderBinding or None')
    context = DashboardContext(binding)

    def register_services(services) -> None:
        services.add(DASHBOARD_CONTEXT_SERVICE_KEY, context)

    register_callbacks = None
    if binding is not None:
        tool_key = binding.structure.tool_key

        def register_callbacks(dash_app, _services) -> None:
            register_general_mina_callback(dash_app, tool_key=tool_key)
            register_carguio_callback(dash_app, tool_key=tool_key)
            register_transporte_callback(dash_app, tool_key=tool_key)
            register_chancado_stmg_callback(dash_app, tool_key=tool_key)
            # Activa la primera card de Planta, sin registrar Tendencia Alimentado.
            register_stockpile_chacay_callback(dash_app, tool_key=tool_key)
            register_tendencia_alimentado_callback(dash_app, tool_key=tool_key)

    return WebModule(
        name='ada-integrated-operations-dashboard',
        page_packages=(_DASHBOARD_PAGE_PACKAGE,),
        asset_layers=(
            ADA_CARD_DISPLAY_ASSET_LAYER,
            ADA_INLINE_ROW_ASSET_LAYER,
            ADA_STOCKPILE_ASSET_LAYER,
            ADA_TIME_SERIES_ASSET_LAYER,
            ADA_EQUIPMENT_IMAGE_ASSET_LAYER,
            ADA_FEEDER_ASSET_LAYER,
            DASHBOARD_ASSET_LAYER,
            MINE_ASSET_LAYER,
            PLANT_ASSET_LAYER,
        ),
        register_services=register_services,
        register_callbacks=register_callbacks,
    )
