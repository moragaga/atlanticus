from ada.web.ui.content_state import (
    ADA_CONTENT_STATE_ASSET_LAYER,
    create_ada_content_state_module,
)


def test_content_state_module_publishes_its_asset_layer() -> None:
    module = create_ada_content_state_module()

    assert module.name == 'ada-content-state'
    assert module.asset_layers == (ADA_CONTENT_STATE_ASSET_LAYER,)
    assert ADA_CONTENT_STATE_ASSET_LAYER.load_order == 130
