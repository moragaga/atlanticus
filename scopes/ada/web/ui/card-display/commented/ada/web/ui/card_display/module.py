from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

# Card Display carga después de los primitives ADA base y antes del shell/inspection.
ADA_CARD_DISPLAY_ASSET_LAYER = AssetLayer(
    name='ada_card_display',
    load_order=160,
    package='ada.web.ui.card_display',
)


def create_ada_card_display_module() -> WebModule:
    # El módulo sólo publica CSS; no registra callbacks ni conoce una Tool concreta.
    return WebModule(
        name='ada-card-display',
        asset_layers=(ADA_CARD_DISPLAY_ASSET_LAYER,),
    )
