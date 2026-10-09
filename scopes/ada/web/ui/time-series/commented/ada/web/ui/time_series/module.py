# Registro independiente del asset UI, reutilizable por distintas aplicaciones.
from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_TIME_SERIES_ASSET_LAYER = AssetLayer(
    name='ada_time_series',
    load_order=182,
    package='ada.web.ui.time_series',
)


def create_ada_time_series_module() -> WebModule:
    return WebModule(name='ada-time-series', asset_layers=(ADA_TIME_SERIES_ASSET_LAYER,))
