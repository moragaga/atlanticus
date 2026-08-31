from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_WAKE_LOCK_ASSET_LAYER = AssetLayer(
    name='ada_wake_lock',
    load_order=9910,
    package='ada.web.application.generic',
    resource_directory='resources/wake_lock',
)


def create_ada_wake_lock_module() -> WebModule:
    return WebModule(
        name='ada-wake-lock',
        asset_layers=(ADA_WAKE_LOCK_ASSET_LAYER,),
    )
