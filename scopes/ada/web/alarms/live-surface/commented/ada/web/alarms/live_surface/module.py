# Registra el asset de presentación sin introducir conexiones a persistencia.
from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_ALARM_LIVE_SURFACE_ASSET_LAYER = AssetLayer(
    name='ada_alarm_live_surface',
    load_order=146,
    package='ada.web.alarms.live_surface',
)


def create_ada_alarm_live_surface_module() -> WebModule:
    return WebModule(
        name='ada-alarm-live-surface',
        asset_layers=(ADA_ALARM_LIVE_SURFACE_ASSET_LAYER,),
    )
