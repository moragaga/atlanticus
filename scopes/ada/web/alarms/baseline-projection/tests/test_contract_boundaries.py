from pathlib import Path

from ada.web.alarms.baseline_projection import (
    AlarmBaselineAnchorKind,
    AlarmBaselinePoint,
    AlarmBaselineProjection,
    AlarmBaselineProjectionError,
    project_alarm_baseline,
)


def test_public_contract_is_exposed() -> None:
    assert AlarmBaselineAnchorKind.COMPONENT.value == 'component'
    assert callable(AlarmBaselinePoint)
    assert callable(AlarmBaselineProjection)
    assert issubclass(AlarmBaselineProjectionError, ValueError)
    assert callable(project_alarm_baseline)


def test_productive_package_does_not_own_ui_or_tool_specific_geometry() -> None:
    root = Path(__file__).parents[1] / 'src' / 'ada' / 'web' / 'alarms' / 'baseline_projection'
    source = '\n'.join(path.read_text(encoding='utf-8') for path in root.glob('*.py'))

    forbidden = (
        'general_mina',
        'carguio',
        'molienda',
        'alarm_points',
        'renderer',
        'html.',
        'dash',
        'css',
        'store_id',
        'callback',
        'Cosmos',
        'SharePoint',
    )
    assert all(value not in source for value in forbidden)
