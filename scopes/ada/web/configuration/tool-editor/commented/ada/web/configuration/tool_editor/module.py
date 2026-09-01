from __future__ import annotations

# Registra los callbacks de Sources y Structure bajo el mismo asset layer.
from ada.web.configuration.tool_editor.callbacks import (
    register_tool_source_editor_callbacks,
)
from ada.web.configuration.tool_editor.structure_callbacks import (
    register_tool_structure_editor_callbacks,
)
from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER = AssetLayer(
    name='ada_tool_configuration_editor',
    load_order=650,
    package='ada.web.configuration.tool_editor',
)


def create_tool_configuration_editor_module() -> WebModule:
    def register_callbacks(app: object, _services: object) -> None:
        register_tool_source_editor_callbacks(app)
        register_tool_structure_editor_callbacks(app)

    return WebModule(
        name='ada-tool-configuration-editor',
        asset_layers=(ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER,),
        register_callbacks=register_callbacks,
    )
