from ada.web.ui.content_state import (
    ADA_CONTENT_STATE_ASSET_LAYER,
    create_ada_content_state_module,
)


def test_content_state_module_publishes_its_asset_layer() -> None:
    module = create_ada_content_state_module()

    assert module.name == 'ada-content-state'
    assert module.asset_layers == (ADA_CONTENT_STATE_ASSET_LAYER,)
    assert ADA_CONTENT_STATE_ASSET_LAYER.load_order == 125


def test_content_state_ui_reexports_core_contract_identity() -> None:
    from ada.web.content_state.core import (
        ContentState as CoreContentState,
        SourceFreshnessCondition as CoreSourceFreshnessCondition,
    )
    from ada.web.ui.content_state import ContentState, SourceFreshnessCondition

    assert ContentState is CoreContentState
    assert SourceFreshnessCondition is CoreSourceFreshnessCondition
