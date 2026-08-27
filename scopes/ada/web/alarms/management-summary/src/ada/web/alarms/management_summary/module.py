from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_ALARM_MANAGEMENT_SUMMARY_ASSET_LAYER = AssetLayer(
    name='ada_alarm_management_summary',
    load_order=130,
    package='ada.web.alarms.management_summary',
)


def create_ada_alarm_management_summary_module() -> WebModule:
    return WebModule(
        name='ada-alarm-management-summary',
        asset_layers=(ADA_ALARM_MANAGEMENT_SUMMARY_ASSET_LAYER,),
    )
