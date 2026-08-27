from ada.web.alarms.status import ADA_ALARM_STATUS_ASSET_LAYER, create_ada_alarm_status_module


def test_alarm_status_module_publishes_own_asset_layer() -> None:
    module = create_ada_alarm_status_module()

    assert module.name == 'ada-alarm-status'
    assert module.asset_layers == (ADA_ALARM_STATUS_ASSET_LAYER,)
    assert ADA_ALARM_STATUS_ASSET_LAYER.name == 'ada_alarm_status'
    assert ADA_ALARM_STATUS_ASSET_LAYER.load_order == 140
