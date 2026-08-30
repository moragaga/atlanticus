from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_CONTENT_STATE_ASSET_LAYER = AssetLayer(
    name='ada_content_state',
    load_order=125,
    package='ada.web.ui.content_state',
)


def create_ada_content_state_module() -> WebModule:
    return WebModule(
        name='ada-content-state',
        asset_layers=(ADA_CONTENT_STATE_ASSET_LAYER,),
    )
