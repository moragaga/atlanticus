from ada.web.ui.card_display import ADA_CARD_DISPLAY_ASSET_LAYER, create_ada_card_display_module


def test_card_display_module_publishes_its_asset_layer() -> None:
    module = create_ada_card_display_module()

    assert module.name == 'ada-card-display'
    assert module.asset_layers == (ADA_CARD_DISPLAY_ASSET_LAYER,)
    assert ADA_CARD_DISPLAY_ASSET_LAYER.load_order == 160
