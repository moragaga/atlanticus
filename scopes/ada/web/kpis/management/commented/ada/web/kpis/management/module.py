from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_KPI_MANAGEMENT_ASSET_LAYER = AssetLayer(
    name='ada_kpi_management',
    load_order=170,
    package='ada.web.kpis.management',
)


def create_ada_kpi_management_module() -> WebModule:
    return WebModule(
        name='ada-kpi-management',
        asset_layers=(ADA_KPI_MANAGEMENT_ASSET_LAYER,),
    )
