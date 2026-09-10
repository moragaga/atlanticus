from ada.web.configuration import ADA_CONFIGURATION_ASSET_LAYER
from ada.web.kpis.definition.web import (
    ADA_KPI_DEFINITION_EDITOR_ASSET_LAYER,
    create_kpi_definition_editor_module,
)


def test_definition_web_module_publishes_standalone_assets() -> None:
    module = create_kpi_definition_editor_module()

    assert module.name == 'ada-kpi-definition'
    assert module.asset_layers == (
        ADA_CONFIGURATION_ASSET_LAYER,
        ADA_KPI_DEFINITION_EDITOR_ASSET_LAYER,
    )
    assert ADA_KPI_DEFINITION_EDITOR_ASSET_LAYER.load_order == 175


def test_definition_web_module_can_omit_shared_configuration_asset() -> None:
    module = create_kpi_definition_editor_module(
        include_configuration_asset=False,
    )

    assert module.asset_layers == (ADA_KPI_DEFINITION_EDITOR_ASSET_LAYER,)
