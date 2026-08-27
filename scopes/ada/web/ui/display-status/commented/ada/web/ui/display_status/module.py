# Registra una capa de assets propia para que los estados visuales no pertenezcan a Global Indicators ni a KPI Body.
from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_DISPLAY_STATUS_ASSET_LAYER = AssetLayer(
    name='ada_display_status',
    load_order=110,
    package='ada.web.ui.display_status',
)


def create_ada_display_status_module() -> WebModule:
    # La capability sólo publica sus CSS/iconos; cada consumidor decide cuándo mostrar un estado.
    return WebModule(
        name='ada-display-status',
        asset_layers=(ADA_DISPLAY_STATUS_ASSET_LAYER,),
    )
