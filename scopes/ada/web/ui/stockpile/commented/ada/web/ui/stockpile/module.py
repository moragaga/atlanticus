from __future__ import annotations

# La capa de assets carga el CSS del propio paquete mediante el módulo Web de Atlanticus.

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_STOCKPILE_ASSET_LAYER = AssetLayer(
    name='ada_stockpile',
    load_order=165,
    package='ada.web.ui.stockpile',
)


# La composición registra el módulo según las dependencias de la aplicación.
def create_ada_stockpile_module() -> WebModule:
    return WebModule(
        name='ada-stockpile',
        asset_layers=(ADA_STOCKPILE_ASSET_LAYER,),
    )
