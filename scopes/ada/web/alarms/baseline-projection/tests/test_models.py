import pytest

from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
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


def test_projection_requires_main_points() -> None:
    with pytest.raises(AlarmBaselineProjectionError, match='requires main points'):
        AlarmBaselineProjection(
            tool_key='tool',
            kind=ToolConfigurationKind.PROCESS,
            main_points=(),
        )


def test_projection_rejects_duplicate_anchor_across_regions() -> None:
    with pytest.raises(AlarmBaselineProjectionError, match='duplicate anchors'):
        AlarmBaselineProjection(
            tool_key='tool',
            kind=ToolConfigurationKind.PROCESS,
            main_points=(_point('component_a', anchor_key='same'),),
            bottom_point=_point('component_b', anchor_key='same'),
        )


def test_projection_rejects_duplicate_component_identity_across_regions() -> None:
    with pytest.raises(AlarmBaselineProjectionError, match='duplicate component keys'):
        AlarmBaselineProjection(
            tool_key='tool',
            kind=ToolConfigurationKind.PROCESS,
            main_points=(_point('component_a', anchor_key='a'),),
            bottom_point=_point('component_a', anchor_key='b'),
        )


def test_projection_rejects_bottom_for_non_process_kind() -> None:
    with pytest.raises(
        AlarmBaselineProjectionError,
        match='only supported for Process',
    ):
        AlarmBaselineProjection(
            tool_key='tool',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            main_points=(_point('component_a'),),
            bottom_point=_point('component_b'),
        )


def test_projection_exposes_rigid_main_and_optional_bottom_contract() -> None:
    projection = AlarmBaselineProjection(
        tool_key=' tool ',
        kind=ToolConfigurationKind.PROCESS,
        main_points=(
            _point('left'),
            _point('center'),
        ),
        bottom_point=_point('detail'),
    )

    assert projection.tool_key == 'tool'
    assert projection.main_component_keys == ('left', 'center')
    assert projection.bottom_component_key == 'detail'
    assert projection.component_keys == ('left', 'center', 'detail')
