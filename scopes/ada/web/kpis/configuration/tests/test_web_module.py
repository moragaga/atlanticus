from ada.web.kpis.configuration.web import (
    ADA_KPI_CONFIGURATION_EDITOR_ASSET_LAYER,
    create_kpi_configuration_editor_module,
)


def test_kpi_configuration_editor_module_publishes_assets() -> None:
    module = create_kpi_configuration_editor_module()

    assert module.name == 'ada-kpi-configuration'
    assert module.asset_layers == (ADA_KPI_CONFIGURATION_EDITOR_ASSET_LAYER,)
    assert ADA_KPI_CONFIGURATION_EDITOR_ASSET_LAYER.load_order == 170
