from ada.web.configuration import (
    ADA_CONFIGURATION_ASSET_LAYER,
    create_ada_configuration_module,
)


def test_configuration_module_publishes_assets() -> None:
    module = create_ada_configuration_module()

    assert module.name == 'ada-configuration'
    assert module.asset_layers == (ADA_CONFIGURATION_ASSET_LAYER,)
    assert ADA_CONFIGURATION_ASSET_LAYER.load_order == 165
