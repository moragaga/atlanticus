import pytest

from ada.configuration.tools import ToolConfigurationKind, ToolScope
from ada.web.alarms.baseline_projection import (
    AlarmBaselineAnchorKind,
    AlarmBaselinePoint,
    AlarmBaselineProjection,
    AlarmBaselineProjectionError,
)


def _point(
    component_key: str,
    *,
    anchor_key: str | None = None,
) -> AlarmBaselinePoint:
    return AlarmBaselinePoint(
        anchor_kind=AlarmBaselineAnchorKind.COMPONENT,
        anchor_key=anchor_key or component_key,
        component_key=component_key,
        display_name=component_key.title(),
        scope=ToolScope.MINE,
    )


def test_point_normalizes_text_values() -> None:
    point = AlarmBaselinePoint(
        anchor_kind=AlarmBaselineAnchorKind.COMPONENT,
        anchor_key=' component_a ',
        component_key=' component_a ',
        display_name=' Component A ',
        scope=ToolScope.MINE,
    )

    assert point.anchor_key == 'component_a'
    assert point.component_key == 'component_a'
    assert point.display_name == 'Component A'


def test_point_rejects_empty_identity() -> None:
    with pytest.raises(AlarmBaselineProjectionError, match='anchor key is required'):
        AlarmBaselinePoint(
            anchor_kind=AlarmBaselineAnchorKind.COMPONENT,
            anchor_key=' ',
            component_key='component_a',
            display_name='Component A',
            scope=ToolScope.MINE,
        )


def test_projection_rejects_duplicate_anchor() -> None:
    with pytest.raises(AlarmBaselineProjectionError, match='duplicate anchors'):
        AlarmBaselineProjection(
            tool_key='tool',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            points=(
                _point('component_a', anchor_key='same'),
                _point('component_b', anchor_key='same'),
            ),
        )


def test_projection_rejects_duplicate_component_identity() -> None:
    with pytest.raises(AlarmBaselineProjectionError, match='duplicate component keys'):
        AlarmBaselineProjection(
            tool_key='tool',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            points=(
                _point('component_a', anchor_key='a'),
                _point('component_a', anchor_key='b'),
            ),
        )


def test_projection_normalizes_tool_key() -> None:
    projection = AlarmBaselineProjection(
        tool_key=' tool ',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        points=(_point('component_a'),),
    )

    assert projection.tool_key == 'tool'
