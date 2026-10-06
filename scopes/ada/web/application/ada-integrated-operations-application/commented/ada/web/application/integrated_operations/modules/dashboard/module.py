from ada.web.application.integrated_operations.modules.dashboard.context import (
    DASHBOARD_CONTEXT_SERVICE_KEY,
    DashboardContext,
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
    context = DashboardContext(binding)

    def register_services(services) -> None:
        services.add(DASHBOARD_CONTEXT_SERVICE_KEY, context)

    return WebModule(
        name='ada-integrated-operations-dashboard',
        page_packages=(_DASHBOARD_PAGE_PACKAGE,),
        # Card Display se carga como asset reusable antes de los assets específicos del dashboard.
        asset_layers=(
            ADA_CARD_DISPLAY_ASSET_LAYER,
            DASHBOARD_ASSET_LAYER,
            MINE_ASSET_LAYER,
            PLANT_ASSET_LAYER,
        ),
        register_services=register_services,
    )
