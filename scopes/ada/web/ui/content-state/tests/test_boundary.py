from __future__ import annotations

import importlib.util

import ada.web.ui.content_state as ui_content_state


def test_content_state_ui_public_api_is_presentation_only() -> None:
    assert tuple(ui_content_state.__all__) == (
        'ADA_CONTENT_STATE_ASSET_LAYER',
        'ContentStatePresentationMode',
        'ContentStateVisual',
        'build_content_state_wrapper',
        'create_ada_content_state_module',
        'resolve_content_state_visual',
    )
    for retired_name in (
        'ContentState',
        'SourceFreshnessCondition',
        'resolve_content_state',
        'resolve_content_state_from_freshness',
    ):
        assert not hasattr(ui_content_state, retired_name)


def test_content_state_ui_has_no_domain_freshness_facade() -> None:
    assert importlib.util.find_spec('ada.web.ui.content_state.freshness') is None
