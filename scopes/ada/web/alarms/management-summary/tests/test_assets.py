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
