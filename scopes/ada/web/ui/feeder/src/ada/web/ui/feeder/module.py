from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_FEEDER_ASSET_LAYER = AssetLayer(
    name='ada_feeder',
    load_order=181,
    package='ada.web.ui.feeder',
)


def create_ada_feeder_module() -> WebModule:
    return WebModule(
        name='ada-feeder',
        asset_layers=(ADA_FEEDER_ASSET_LAYER,),
    )
