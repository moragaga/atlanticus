from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_ALARM_STATUS_ASSET_LAYER = AssetLayer(
    name='ada_alarm_status',
    load_order=140,
    package='ada.web.alarms.status',
)


def create_ada_alarm_status_module() -> WebModule:
    return WebModule(
        name='ada-alarm-status',
        asset_layers=(ADA_ALARM_STATUS_ASSET_LAYER,),
    )
