from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

# Capa de assets exclusiva de ADA. Se carga después del workaround de sesión para mantener
# cada responsabilidad aislada y sin modificar Atlanticus Web genérico.
ADA_WAKE_LOCK_ASSET_LAYER = AssetLayer(
    name='ada_wake_lock',
    load_order=9910,
    package='ada.web.application.generic',
    resource_directory='resources/wake_lock',
)


def create_ada_wake_lock_module() -> WebModule:
    # El módulo no expone configuración ni callbacks: sólo publica el JavaScript que administra
    # el Screen Wake Lock según la ruta y visibilidad actuales del navegador.
    return WebModule(
        name='ada-wake-lock',
        asset_layers=(ADA_WAKE_LOCK_ASSET_LAYER,),
    )
