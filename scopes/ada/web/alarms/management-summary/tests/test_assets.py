from pathlib import Path

from ada.web.alarms.management_summary import ADA_ALARM_MANAGEMENT_SUMMARY_ASSET_LAYER

PACKAGE_ROOT = Path(__file__).parents[1] / 'src/ada/web/alarms/management_summary'


def test_css_manifest_contains_only_management_summary_styles() -> None:
    css_list = (PACKAGE_ROOT / 'resources/css/css.list').read_text(encoding='utf-8').splitlines()
    css = (PACKAGE_ROOT / 'resources/css/10-management-summary.css').read_text(encoding='utf-8')

    assert css_list == ['10-management-summary.css']
    assert '.ada-alarm-management-summary {' in css
    assert "[data-tone='critical']" in css
    assert 'ada-alarm-notifications-status' not in css


def test_asset_layer_points_to_canonical_package() -> None:
    assert ADA_ALARM_MANAGEMENT_SUMMARY_ASSET_LAYER.package == 'ada.web.alarms.management_summary'


def test_group_is_neutral_and_percentage_matches_progress_tone() -> None:
    css = (PACKAGE_ROOT / 'resources/css/10-management-summary.css').read_text(encoding='utf-8')

    assert "[data-tone='attention']\n    .ada-alarm-management-summary__percentage-value" in css
    assert "[data-tone='critical']\n    .ada-alarm-management-summary__percentage-value" in css
    assert '.ada-alarm-management-summary__group-value {' in css
    assert 'color: var(--ada-color-text-primary);' in css
    assert 'background: var(--ada-color-surface-emphasis);' in css
    assert '#198754' not in css
    assert '#28A745' not in css


def test_management_summary_uses_pelambres_responsive_typography() -> None:
    css = (PACKAGE_ROOT / 'resources/css/10-management-summary.css').read_text(encoding='utf-8')

    assert '@media only screen and (min-width: 350px) and (max-width: 1279.98px)' in css
    assert '@media only screen and (min-width: 1280px)' in css
    assert '@media only screen and (min-width: 2560px)' in css


def test_management_summary_visual_calibration_scales_videowall() -> None:
    css = (PACKAGE_ROOT / 'resources/css/10-management-summary.css').read_text(encoding='utf-8')
    assert '.ada-alarm-management-summary__label { font-size: .6rem; }' in css
    assert '.ada-alarm-management-summary__value { font-size: .78rem; }' in css
