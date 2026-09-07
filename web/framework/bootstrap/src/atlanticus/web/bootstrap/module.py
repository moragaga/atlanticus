from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

BOOTSTRAP_ASSET_LAYER = AssetLayer(
    name='atlanticus_web_bootstrap',
    load_order=40,
    package='atlanticus.web.bootstrap',
    resource_directory='resources',
)


def create_bootstrap_web_module() -> WebModule:
    return WebModule(
        name='bootstrap',
        asset_layers=(BOOTSTRAP_ASSET_LAYER,),
    )
