from __future__ import annotations

from ada.web.configuration.manager_tools.callbacks import register_manager_tools_callbacks
from ada.web.configuration.tool_editor import (
    ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER,
    register_tool_source_editor_callbacks,
)
from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_MANAGER_TOOLS_ASSET_LAYER = AssetLayer(
    name='ada_manager_tools',
    load_order=640,
    package='ada.web.configuration.manager_tools',
)


def create_manager_tools_module() -> WebModule:
    def register_callbacks(app: object, _services: object) -> None:
        register_manager_tools_callbacks(app)
        register_tool_source_editor_callbacks(app)

    return WebModule(
        name='ada-manager-tools',
        page_packages=('ada.web.configuration.manager_tools.pages',),
        asset_layers=(
            ADA_MANAGER_TOOLS_ASSET_LAYER,
            ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER,
        ),
        register_callbacks=register_callbacks,
    )
