from ada.contracts.tools.enums import ToolScope
from ada.web.application.integrated_operations.modules.dashboard.global_indicators import (
    INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS,
)


def test_product_global_indicator_catalog_exposes_authoring_collection() -> None:
    assert len(INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS) == 8
    assert tuple(
        binding.definition.key for binding in INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS
    ) == tuple(f'test_indicator_{index}' for index in range(1, 9))
    assert INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS[0].scopes == (ToolScope.MINE,)
    assert INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS[1].scopes == (
        ToolScope.MINE,
        ToolScope.PLANT,
    )
    assert all(
        binding.scopes == (ToolScope.PLANT,)
        for binding in INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS[2:]
    )
