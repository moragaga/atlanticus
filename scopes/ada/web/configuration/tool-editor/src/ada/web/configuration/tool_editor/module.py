from __future__ import annotations

from ada.web.configuration.tool_editor.callbacks import (
    register_tool_source_editor_callbacks,
)
from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER = AssetLayer(
    name='ada_tool_configuration_editor',
    load_order=650,
    package='ada.web.configuration.tool_editor',
)


def create_tool_configuration_editor_module() -> WebModule:
    return WebModule(
        name='ada-tool-configuration-editor',
        asset_layers=(ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER,),
        register_callbacks=lambda app, _services: register_tool_source_editor_callbacks(app),
    )
