from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

# Capa Bootstrap opt-in. Se carga después del shell base y antes de las
# capabilities, para que cada composición conserve la última palabra sobre
# su geometría sin reimplementar los controles visuales.
BOOTSTRAP_ASSET_LAYER = AssetLayer(
    name='atlanticus_web_bootstrap',
    load_order=40,
    package='atlanticus.web.bootstrap',
    resource_directory='resources',
)


def create_bootstrap_web_module() -> WebModule:
    # El módulo no registra servicios ni callbacks: sólo publica el contrato
    # visual Bootstrap acotado que una composición decide consumir.
    return WebModule(
        name='bootstrap',
        asset_layers=(BOOTSTRAP_ASSET_LAYER,),
    )
