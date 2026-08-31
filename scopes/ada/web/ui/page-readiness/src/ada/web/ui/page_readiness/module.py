from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_PAGE_READINESS_ASSET_LAYER = AssetLayer(
    name='ada_page_readiness',
    load_order=9920,
    package='ada.web.ui.page_readiness',
    resource_directory='resources',
)


def create_ada_page_readiness_module() -> WebModule:
    return WebModule(
        name='ada-page-readiness',
        asset_layers=(ADA_PAGE_READINESS_ASSET_LAYER,),
    )
