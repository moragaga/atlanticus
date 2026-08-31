from __future__ import annotations

import pytest

from ada.web.ui.page_readiness import (
    COMPONENT_KEY_PROPERTY,
    RENDER_READY_PROPERTY,
    build_render_ready_attributes,
)


def test_render_ready_attributes_reuse_stable_component_identity() -> None:
    assert COMPONENT_KEY_PROPERTY == 'data-ada-component-key'
    assert RENDER_READY_PROPERTY == 'data-ada-render-ready'
    assert build_render_ready_attributes('  crusher_feed  ') == {
        COMPONENT_KEY_PROPERTY: 'crusher_feed',
        RENDER_READY_PROPERTY: 'false',
    }
    assert (
        build_render_ready_attributes('crusher_feed', ready=True)[RENDER_READY_PROPERTY] == 'true'
    )


@pytest.mark.parametrize('value', ['', '   ', None, 3])
def test_render_ready_attributes_reject_invalid_component_keys(value: object) -> None:
    with pytest.raises(ValueError, match='non-empty string'):
        build_render_ready_attributes(value)  # type: ignore[arg-type]
