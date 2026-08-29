from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_TIME_STATUS_ASSET_LAYER = AssetLayer(
    name='ada_time_status',
    load_order=150,
    package='ada.web.ui.time_status',
)


def create_ada_time_status_module() -> WebModule:
    return WebModule(
        name='ada-time-status',
        asset_layers=(ADA_TIME_STATUS_ASSET_LAYER,),
    )
