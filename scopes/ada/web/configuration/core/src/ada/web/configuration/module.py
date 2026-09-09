from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_CONFIGURATION_ASSET_LAYER = AssetLayer(
    name='ada_configuration',
    load_order=165,
    package='ada.web.configuration',
)


def create_ada_configuration_module() -> WebModule:
    return WebModule(
        name='ada-configuration',
        asset_layers=(ADA_CONFIGURATION_ASSET_LAYER,),
    )
