from ada.web.alarms.baseline_surface import (
    ADA_ALARM_BASELINE_SURFACE_ASSET_LAYER,
    create_ada_alarm_baseline_surface_module,
)


def test_module_registers_only_baseline_surface_assets() -> None:
    module = create_ada_alarm_baseline_surface_module()

    assert module.name == 'ada-alarm-baseline-surface'
    assert module.asset_layers == (ADA_ALARM_BASELINE_SURFACE_ASSET_LAYER,)
    assert ADA_ALARM_BASELINE_SURFACE_ASSET_LAYER.name == 'ada_alarm_baseline_surface'
    assert ADA_ALARM_BASELINE_SURFACE_ASSET_LAYER.load_order == 150
    assert ADA_ALARM_BASELINE_SURFACE_ASSET_LAYER.package == 'ada.web.alarms.baseline_surface'
