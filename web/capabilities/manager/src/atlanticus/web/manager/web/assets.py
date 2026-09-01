from atlanticus.web.assets import AssetLayer

ATLANTICUS_MANAGER_LAYER_NAME = 'atlanticus_web_manager'


def manager_asset_layer() -> AssetLayer:
    return AssetLayer(
        name=ATLANTICUS_MANAGER_LAYER_NAME,
        load_order=300,
        package='atlanticus.web.manager',
    )
