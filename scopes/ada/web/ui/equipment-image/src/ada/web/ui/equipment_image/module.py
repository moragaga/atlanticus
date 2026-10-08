from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_EQUIPMENT_IMAGE_ASSET_LAYER = AssetLayer(
    name='ada_equipment_image',
    load_order=115,
    package='ada.web.ui.equipment_image',
)


def create_ada_equipment_image_module() -> WebModule:
    return WebModule(
        name='ada-equipment-image',
        asset_layers=(ADA_EQUIPMENT_IMAGE_ASSET_LAYER,),
    )
