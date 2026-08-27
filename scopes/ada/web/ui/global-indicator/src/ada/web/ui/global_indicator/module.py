from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_GLOBAL_INDICATOR_ASSET_LAYER = AssetLayer(
    name='ada_global_indicator',
    load_order=120,
    package='ada.web.ui.global_indicator',
)


def create_ada_global_indicator_module() -> WebModule:
    return WebModule(
        name='ada-global-indicator',
        asset_layers=(ADA_GLOBAL_INDICATOR_ASSET_LAYER,),
    )
