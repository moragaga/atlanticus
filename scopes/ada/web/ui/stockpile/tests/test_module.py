from importlib import resources

from ada.web.ui.stockpile import ADA_STOCKPILE_ASSET_LAYER, create_ada_stockpile_module


def test_stockpile_asset_layer_is_reusable_and_has_css_resources():
    module = create_ada_stockpile_module()
    assert module.name == 'ada-stockpile'
    assert module.asset_layers == (ADA_STOCKPILE_ASSET_LAYER,)
    package_resources = resources.files('ada.web.ui.stockpile')
    assert package_resources.joinpath('resources/css/css.list').is_file()
    assert package_resources.joinpath('resources/css/10-stockpile.css').is_file()
