from ada.contracts.tools.enums import ToolScope
from ada.web.application.integrated_operations.modules.dashboard.global_indicators import (
    INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS,
)


def test_product_global_indicator_catalog_exposes_configured_test_indicator() -> None:
    assert len(INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS) == 1
    binding = INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS[0]

    assert binding.definition.key == 'test_indicator'
    assert tuple(item.key for item in binding.definition.measurements) == ('day', 'week')
    assert binding.scopes == (ToolScope.MINE, ToolScope.PLANT)
