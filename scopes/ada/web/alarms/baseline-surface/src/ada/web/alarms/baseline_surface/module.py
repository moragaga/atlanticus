from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_ALARM_BASELINE_SURFACE_ASSET_LAYER = AssetLayer(
    name='ada_alarm_baseline_surface',
    load_order=150,
    package='ada.web.alarms.baseline_surface',
)


def create_ada_alarm_baseline_surface_module() -> WebModule:
    return WebModule(
        name='ada-alarm-baseline-surface',
        asset_layers=(ADA_ALARM_BASELINE_SURFACE_ASSET_LAYER,),
    )
