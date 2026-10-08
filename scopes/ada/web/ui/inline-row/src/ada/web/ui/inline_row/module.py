from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_INLINE_ROW_ASSET_LAYER = AssetLayer(
    name='ada_inline_row',
    load_order=190,
    package='ada.web.ui.inline_row',
)


def create_ada_inline_row_module() -> WebModule:
    return WebModule(
        name='ada-inline-row',
        asset_layers=(ADA_INLINE_ROW_ASSET_LAYER,),
    )
