# Registra los recursos visuales ADA sin acoplarlos a una composición concreta.
from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_BRANDING_ASSET_LAYER = AssetLayer(
    name='ada_branding',
    load_order=200,
    package='ada.web.ui.branding',
)

# Fuentes públicas para que shells/composiciones puedan inyectar logos sin duplicar assets.
DEFAULT_OPERATIONAL_BRAND_LOGO_SRC = (
    f'/assets/{ADA_BRANDING_ASSET_LAYER.target_name}/img/ada-operational-primary.svg'
)
DEFAULT_PELAMBRES_BRAND_LOGO_SRC = (
    f'/assets/{ADA_BRANDING_ASSET_LAYER.target_name}/img/amsa-pelambres-primary.png'
)


def create_ada_branding_module() -> WebModule:
    return WebModule(
        name='ada-branding',
        asset_layers=(ADA_BRANDING_ASSET_LAYER,),
    )
