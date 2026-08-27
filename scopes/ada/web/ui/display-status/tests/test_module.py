from ada.web.ui.display_status import (
    ADA_DISPLAY_STATUS_ASSET_LAYER,
    create_ada_display_status_module,
)


def test_display_status_module_publishes_its_asset_layer() -> None:
    module = create_ada_display_status_module()

    assert module.name == 'ada-display-status'
    assert module.asset_layers == (ADA_DISPLAY_STATUS_ASSET_LAYER,)
    assert ADA_DISPLAY_STATUS_ASSET_LAYER.load_order == 110
