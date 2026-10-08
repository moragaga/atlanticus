from ada.web.ui.inline_row import ADA_INLINE_ROW_ASSET_LAYER, create_ada_inline_row_module


def test_inline_row_module_publishes_css_layer():
    module = create_ada_inline_row_module()
    assert module.name == 'ada-inline-row'
    assert module.asset_layers == (ADA_INLINE_ROW_ASSET_LAYER,)
    assert ADA_INLINE_ROW_ASSET_LAYER.load_order == 170
