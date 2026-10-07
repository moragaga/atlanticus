from ada.web.application.integrated_operations.modules.dashboard.context import (
    DASHBOARD_CONTEXT_SERVICE_KEY,
    DashboardContext,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.carguio.runtime import (
    register_carguio_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.general_mina.runtime import (
    register_general_mina_callback,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.module import (
    MINE_ASSET_LAYER,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.module import (
    PLANT_ASSET_LAYER,
)
from ada.web.operational_render_binding import OperationalRenderBinding
from ada.web.ui.card_display import ADA_CARD_DISPLAY_ASSET_LAYER
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

    # El contexto conserva el binding operacional y permite que el layout exista aun sin Tool publicada.
    context = DashboardContext(binding)

    def register_services(services) -> None:
        services.add(DASHBOARD_CONTEXT_SERVICE_KEY, context)

    # Sólo una Tool resuelta tiene Component KPI Stores. Sin binding no se registran Inputs inexistentes.
    register_callbacks = None
    if binding is not None:
        tool_key = binding.structure.tool_key

        # Cada componente operacional tiene un callback coordinador y sus cards agregan Outputs allí.
        def register_callbacks(dash_app, _services) -> None:
            register_general_mina_callback(dash_app, tool_key=tool_key)
            register_carguio_callback(dash_app, tool_key=tool_key)

    return WebModule(
        name='ada-integrated-operations-dashboard',
        page_packages=(_DASHBOARD_PAGE_PACKAGE,),
        # Card Display se carga antes de los assets específicos del dashboard y de sus scopes.
        asset_layers=(
            ADA_CARD_DISPLAY_ASSET_LAYER,
            DASHBOARD_ASSET_LAYER,
            MINE_ASSET_LAYER,
            PLANT_ASSET_LAYER,
        ),
        register_services=register_services,
        register_callbacks=register_callbacks,
    )
