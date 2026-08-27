from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_OPERATIONAL_HEADER_ASSET_LAYER = AssetLayer(
    name='ada_operational_header',
    load_order=220,
    package='ada.web.shell.header',
)


def create_ada_operational_header_module() -> WebModule:
    return WebModule(
        name='ada-operational-header',
        asset_layers=(ADA_OPERATIONAL_HEADER_ASSET_LAYER,),
    )
