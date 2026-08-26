from __future__ import annotations

from ada.web.shell.navigation.callbacks import register_ada_navigation_callbacks
from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_NAVIGATION_ASSET_LAYER = AssetLayer(
    name='ada_navigation',
    load_order=210,
    package='ada.web.shell.navigation',
)


def create_ada_navigation_presentation_module() -> WebModule:
    return WebModule(
        name='ada-navigation',
        asset_layers=(ADA_NAVIGATION_ASSET_LAYER,),
        register_callbacks=register_ada_navigation_callbacks,
    )
