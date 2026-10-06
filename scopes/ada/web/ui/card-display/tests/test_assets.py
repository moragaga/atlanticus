import re
from importlib import resources

import ada.web.ui.card_display as card_display_package


def _css() -> str:
    return (
        resources.files(card_display_package)
        .joinpath('resources/css/10-card-display.css')
        .read_text(encoding='utf-8')
    )


def test_card_display_css_uses_brand_and_root_tokens_without_hardcoded_colors() -> None:
    css = _css()

    assert 'var(--primary-background, var(--ada-color-surface-primary))' in css
    assert 'var(--custom-text-color, var(--ada-color-text-primary))' in css
    assert 'var(--primary-border-color, var(--ada-color-border-primary))' in css
    assert re.search(r'#[0-9a-fA-F]{3,8}\b', css) is None
    assert 'rgb(' not in css.lower()
    assert 'hsl(' not in css.lower()


def test_card_display_css_exposes_canonical_integrated_operations_card_geometry() -> None:
    css = _css()

    assert 'display: grid;' in css
    assert 'grid-template-rows: minmax(0, 1fr) auto auto;' in css
    assert 'border-radius: .3rem;' in css
    assert 'padding: .12rem .28rem;' in css
    assert 'font-size: .54rem;' in css
    assert 'font-weight: 700;' in css
    assert 'line-height: 1.2;' in css
    assert 'text-overflow: ellipsis;' in css
    assert 'white-space: nowrap;' in css


def test_card_display_empty_optional_slots_do_not_change_card_geometry() -> None:
    css = _css()

    assert '.ada-card-display__regions:empty {' in css
    assert '.ada-card-display__footer:empty {' in css
    assert '.ada-card-display__overlay:empty {' in css
    assert '--ada-card-display-region-columns' in css
    assert '--ada-card-display-region-gap' in css


def test_card_display_is_container_ready_and_has_no_tool_breakpoints() -> None:
    css = _css()

    assert 'container-type: inline-size;' in css
    assert 'container-name: ada-card-display;' in css
    assert '@media' not in css


def test_card_display_asset_list_is_minimal() -> None:
    asset_list = (
        resources.files(card_display_package)
        .joinpath('resources/css/css.list')
        .read_text(encoding='utf-8')
        .splitlines()
    )

    assert asset_list == ['10-card-display.css']
