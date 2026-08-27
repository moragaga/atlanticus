from __future__ import annotations

from importlib.resources import files
from xml.etree import ElementTree

from ada.web.ui.display_status import (
    ADA_DISPLAY_STATUS_ASSET_LAYER,
    DisplayStatus,
    build_display_status_icon,
    resolve_status_visual,
)


def _prop(component, name: str):
    return component.to_plotly_json()['props'][name]


def test_degraded_statuses_resolve_to_shared_assets() -> None:
    expected = {
        DisplayStatus.NOT_MAPPED: 'not-mapped.svg',
        DisplayStatus.EMPTY: 'empty-data.svg',
        DisplayStatus.INVALID: 'invalid-data.svg',
        DisplayStatus.ERROR: 'internal-error.svg',
    }

    for status, asset_name in expected.items():
        visual = resolve_status_visual(status)
        assert visual is not None
        assert visual.asset_name == asset_name
        assert visual.asset_url == (
            f'/assets/{ADA_DISPLAY_STATUS_ASSET_LAYER.target_name}/img/status/{asset_name}'
        )

    assert resolve_status_visual(DisplayStatus.OK) is None


def test_status_icon_is_shared_and_allows_consumer_class() -> None:
    icon = build_display_status_icon(DisplayStatus.ERROR, class_name='kpi__status-icon')

    assert icon is not None
    assert _prop(icon, 'src').endswith('/img/status/internal-error.svg')
    assert _prop(icon, 'alt') == 'Error interno'
    assert _prop(icon, 'className') == 'ada-display-status__icon kpi__status-icon'
    assert build_display_status_icon(DisplayStatus.OK) is None


def test_status_assets_exist_and_are_valid_svg_documents() -> None:
    root = files('ada.web.ui.display_status').joinpath('resources/img/status')
    for name in ('not-mapped.svg', 'empty-data.svg', 'invalid-data.svg', 'internal-error.svg'):
        resource = root.joinpath(name)
        assert resource.is_file()
        ElementTree.fromstring(resource.read_text(encoding='utf-8'))


def test_internal_error_viewbox_matches_bootstrap_path_coordinates() -> None:
    resource = files('ada.web.ui.display_status').joinpath(
        'resources/img/status/internal-error.svg'
    )
    root = ElementTree.fromstring(resource.read_text(encoding='utf-8'))

    assert root.attrib['viewBox'] == '0 0 16 16'
