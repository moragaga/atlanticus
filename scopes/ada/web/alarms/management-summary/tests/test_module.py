from ada.web.alarms.management_summary import (
    ADA_ALARM_MANAGEMENT_SUMMARY_ASSET_LAYER,
    create_ada_alarm_management_summary_module,
)


def test_module_owns_management_summary_assets() -> None:
    module = create_ada_alarm_management_summary_module()

    assert module.name == 'ada-alarm-management-summary'
    assert module.asset_layers == (ADA_ALARM_MANAGEMENT_SUMMARY_ASSET_LAYER,)
    assert ADA_ALARM_MANAGEMENT_SUMMARY_ASSET_LAYER.name == 'ada_alarm_management_summary'
    assert ADA_ALARM_MANAGEMENT_SUMMARY_ASSET_LAYER.load_order == 130
