from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.index import IndexContribution
from atlanticus.web.modules import WebModule

ADA_UI_ASSET_LAYER = AssetLayer(
    name='ada_ui_core',
    load_order=100,
    package='ada.web.ui.core',
)

_INTER_STYLESHEET = (
    'https://fonts.googleapis.com/css2?'
    'family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&display=swap'
)
_BOOTSTRAP_ICONS_STYLESHEET = (
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css'
)


def create_ada_ui_module() -> WebModule:
    return WebModule(
        name='ada-ui',
        asset_layers=(ADA_UI_ASSET_LAYER,),
        index=IndexContribution(
            head_fragments=(
                '<link rel="preconnect" href="https://fonts.googleapis.com">',
                '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
                f'<link rel="stylesheet" href="{_INTER_STYLESHEET}">',
                f'<link rel="stylesheet" href="{_BOOTSTRAP_ICONS_STYLESHEET}">',
            ),
        ),
    )
