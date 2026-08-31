from ada.web.configuration.manager_tools import (
    ADA_MANAGER_TOOLS_ASSET_LAYER,
    create_manager_tools_module,
)
from ada.web.configuration.tool_editor import ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER


def test_manager_tools_module_owns_route_and_composes_source_assets() -> None:
    module = create_manager_tools_module()

    assert module.name == 'ada-manager-tools'
    assert module.page_packages == ('ada.web.configuration.manager_tools.pages',)
    assert module.asset_layers == (
        ADA_MANAGER_TOOLS_ASSET_LAYER,
        ADA_TOOL_CONFIGURATION_EDITOR_ASSET_LAYER,
    )
