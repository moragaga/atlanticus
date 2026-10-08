from ada.web.ui.equipment_image import (
    ADA_EQUIPMENT_IMAGE_ASSET_LAYER,
    create_ada_equipment_image_module,
)


def test_equipment_image_asset_layer_contract():
    module = create_ada_equipment_image_module()
    assert module.name == 'ada-equipment-image'
    assert module.asset_layers == (ADA_EQUIPMENT_IMAGE_ASSET_LAYER,)
    assert ADA_EQUIPMENT_IMAGE_ASSET_LAYER.load_order == 115
