from ada.web.configuration.tool_editor import (
    ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER,
    create_tool_configuration_editor_module,
)


def test_editor_module_registers_single_asset_layer() -> None:
    module = create_tool_configuration_editor_module()

    assert module.name == 'ada-tool-configuration-editor'
    assert module.asset_layers == (ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER,)
    assert ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER.name == 'ada_tool_configuration_editor'
    assert ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER.load_order == 650
