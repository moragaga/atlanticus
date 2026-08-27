from ada.web.ui.global_indicator import (
    ADA_GLOBAL_INDICATOR_ASSET_LAYER,
    create_ada_global_indicator_module,
)


def test_global_indicator_module_declares_its_asset_layer() -> None:
    module = create_ada_global_indicator_module()

    assert module.name == 'ada-global-indicator'
    assert module.asset_layers == (ADA_GLOBAL_INDICATOR_ASSET_LAYER,)
    assert ADA_GLOBAL_INDICATOR_ASSET_LAYER.load_order == 120
