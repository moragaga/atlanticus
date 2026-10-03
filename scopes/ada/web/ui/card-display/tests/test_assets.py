import re
from importlib import resources
from pathlib import Path

import ada.web.ui.card_display as card_display_package


def _css() -> str:
    return (
        resources.files(card_display_package)
        .joinpath('resources/css/10-card-display.css')
        .read_text(encoding='utf-8')
    )


def test_card_display_css_uses_root_tokens_without_hardcoded_colors() -> None:
    css = _css()

    assert 'var(--ada-color-surface-primary)' in css
    assert 'var(--ada-color-text-primary)' in css
    assert 'var(--ada-color-border-primary)' in css
    assert re.search(r'#[0-9a-fA-F]{3,8}\b', css) is None
    assert 'rgb(' not in css.lower()
    assert 'hsl(' not in css.lower()


def test_card_display_exposes_scale_density_and_region_column_contracts() -> None:
    css = _css()

    assert '--ada-card-display-scale' in css
    assert '--ada-card-display-density' in css
    assert '--ada-card-display-region-columns' in css
    assert '--ada-card-display-font-size' in css
    assert '--ada-card-display-icon-size' in css
    assert '.ada-card-display__icon {' in css


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
