from __future__ import annotations

from ada.web.ui.page_readiness import (
    ADA_PAGE_READINESS_ASSET_LAYER,
    create_ada_page_readiness_module,
)


def test_module_publishes_page_readiness_assets_without_tool_contracts() -> None:
    module = create_ada_page_readiness_module()

    assert module.name == 'ada-page-readiness'
    assert module.asset_layers == (ADA_PAGE_READINESS_ASSET_LAYER,)
    assert ADA_PAGE_READINESS_ASSET_LAYER.name == 'ada_page_readiness'
    assert ADA_PAGE_READINESS_ASSET_LAYER.load_order == 9920
    assert ADA_PAGE_READINESS_ASSET_LAYER.package == 'ada.web.ui.page_readiness'
