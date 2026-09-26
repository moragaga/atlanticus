from __future__ import annotations

from application.modules.example.callbacks import register_callbacks
from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule


def create_example_module() -> WebModule:
    return WebModule(
        name='starter-example',
        page_packages=('application.modules.example.pages',),
        asset_layers=(
            AssetLayer(
                name='starter-example',
                load_order=9100,
                package='application.modules.example',
            ),
        ),
        register_callbacks=register_callbacks,
    )
