# Espejo pedagógico: este archivo conserva exactamente la lógica del código productivo.
# Capability genérica del Configuration Manager de Atlanticus. Mantiene contratos y UI administrativa sin conocer dominios ni persistencias concretas.
# Los comentarios explican la intención arquitectónica; no agregan ramas, estado ni comportamiento.

from atlanticus.web.assets import AssetLayer

ATLANTICUS_MANAGER_LAYER_NAME = 'atlanticus_web_manager'


def manager_asset_layer() -> AssetLayer:
    return AssetLayer(
        name=ATLANTICUS_MANAGER_LAYER_NAME,
        load_order=300,
        package='atlanticus.web.manager',
    )
