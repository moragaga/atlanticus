from ada.web.kpis.management import (
    ADA_KPI_MANAGEMENT_ASSET_LAYER,
    create_ada_kpi_management_module,
)


def test_kpi_management_module_publishes_assets() -> None:
    module = create_ada_kpi_management_module()

    assert module.name == 'ada-kpi-management'
    assert module.asset_layers == (ADA_KPI_MANAGEMENT_ASSET_LAYER,)
    assert ADA_KPI_MANAGEMENT_ASSET_LAYER.load_order == 170
