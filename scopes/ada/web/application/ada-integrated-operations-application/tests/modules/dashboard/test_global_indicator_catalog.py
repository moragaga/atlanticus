from ada.web.application.integrated_operations.modules.dashboard.global_indicators import (
    INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS,
)


def test_product_global_indicator_catalog_stays_empty_without_authoritative_kpi_keys() -> None:
    assert INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS == ()
