from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

# Capa posterior a los runtime JS de Session/Wake Lock; sólo actúa cuando existe un scope de readiness.
ADA_PAGE_READINESS_ASSET_LAYER = AssetLayer(
    name='ada_page_readiness',
    load_order=9920,
    package='ada.web.ui.page_readiness',
    resource_directory='resources',
)


def create_ada_page_readiness_module() -> WebModule:
    # El módulo publica mecánica CSS/JS; no contiene loaders ni nombres de Tools.
    return WebModule(
        name='ada-page-readiness',
        asset_layers=(ADA_PAGE_READINESS_ASSET_LAYER,),
    )
