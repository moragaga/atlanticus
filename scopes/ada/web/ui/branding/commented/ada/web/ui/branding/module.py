# Registra los assets propios de la identidad operacional ADA como una capa independiente. El
# Header sólo tendrá que anclar el componente y no conocer dónde viven sus imágenes o estilos.
from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_BRANDING_ASSET_LAYER = AssetLayer(
    name='ada_branding',
    load_order=200,
    package='ada.web.ui.branding',
)

# La URL deriva del nombre estable de la capa publicada por Atlanticus Web; evita convertir la
# imagen a base64 dentro de cada Header y permite cachearla como asset normal del navegador.
DEFAULT_OPERATIONAL_BRAND_LOGO_SRC = (
    f'/assets/{ADA_BRANDING_ASSET_LAYER.target_name}/img/ada-operational-primary.svg'
)


def create_ada_branding_module() -> WebModule:
    return WebModule(
        name='ada-branding',
        asset_layers=(ADA_BRANDING_ASSET_LAYER,),
    )
