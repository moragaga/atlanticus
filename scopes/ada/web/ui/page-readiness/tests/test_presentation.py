from __future__ import annotations

import pytest
from dash import html

from ada.web.ui.page_readiness import (
    DEFAULT_PAGE_READINESS_SETTLE_MS,
    build_page_readiness_scope,
)


def test_scope_keeps_content_and_injected_loader_separate() -> None:
    component = build_page_readiness_scope(
        content=html.Div('Operational content', id='content'),
        loader=html.Div('Tool loader', id='loader'),
    )

    props = component.to_plotly_json()['props']
    assert props['className'] == 'ada-page-readiness'
    assert props['data-ada-page-readiness'] == 'true'
    assert props['data-ada-page-readiness-enabled'] == 'true'
    assert props['data-ada-page-readiness-state'] == 'loading'
    assert props['data-ada-page-readiness-settle-ms'] == str(DEFAULT_PAGE_READINESS_SETTLE_MS)
    assert props['aria-busy'] == 'true'
    assert component.children[0].className == 'ada-page-readiness__content'
    assert component.children[1].className == 'ada-page-readiness__loader'
    assert component.children[1].hidden is False
    assert component.children[1].children.id == 'loader'


def test_disabled_scope_is_ready_without_removing_content() -> None:
    component = build_page_readiness_scope(
        content=html.Div('Content'),
        loader=html.Div('Loader'),
        enabled=False,
    )

    props = component.to_plotly_json()['props']
    assert props['data-ada-page-readiness-enabled'] == 'false'
    assert props['data-ada-page-readiness-state'] == 'ready'
    assert props['aria-busy'] == 'false'
    assert component.children[1].hidden is True


@pytest.mark.parametrize('value', [True, 1.5, -1, 2001])
def test_scope_rejects_invalid_settle_values(value: object) -> None:
    with pytest.raises(ValueError, match='settle_ms'):
        build_page_readiness_scope(
            content=html.Div('Content'),
            loader=html.Div('Loader'),
            settle_ms=value,  # type: ignore[arg-type]
        )
