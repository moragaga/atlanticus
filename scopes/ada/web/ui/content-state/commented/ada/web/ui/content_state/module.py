from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

# La capa queda después de Display Status y Global Indicator base, pero antes de Time Status.
ADA_CONTENT_STATE_ASSET_LAYER = AssetLayer(
    name='ada_content_state',
    load_order=125,
    package='ada.web.ui.content_state',
)


def create_ada_content_state_module() -> WebModule:
    # El módulo solo publica assets; no conoce PI, Dispatch ni composición de Tools.
    return WebModule(
        name='ada-content-state',
        asset_layers=(ADA_CONTENT_STATE_ASSET_LAYER,),
    )
