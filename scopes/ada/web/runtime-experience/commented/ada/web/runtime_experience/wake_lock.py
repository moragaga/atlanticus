from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

# Wake Lock sigue siendo una capability ADA operacional independiente de la aplicación que la monta.
ADA_WAKE_LOCK_ASSET_LAYER = AssetLayer(
    name='ada_wake_lock',
    load_order=9910,
    package='ada.web.runtime_experience',
    resource_directory='resources/wake_lock',
)


def create_ada_wake_lock_module() -> WebModule:
    # El módulo sólo publica su asset; no crea runtime, callbacks ni dependencias de aplicación.
    return WebModule(
        name='ada-wake-lock',
        asset_layers=(ADA_WAKE_LOCK_ASSET_LAYER,),
    )
