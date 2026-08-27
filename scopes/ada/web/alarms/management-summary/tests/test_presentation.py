from dash.development.base_component import Component

from ada.web.alarms.management_summary import (
    AlarmManagementSummaryArea,
    AlarmManagementSummarySegmentState,
    AlarmManagementSummaryState,
    AlarmManagementSummaryTone,
    build_alarm_management_summary,
)


def _props(component: Component):
    return component.to_plotly_json()['props']


def _walk(component: Component):
    yield component
    children = getattr(component, 'children', None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if isinstance(child, Component):
            yield from _walk(child)


def _state() -> AlarmManagementSummaryState:
    return AlarmManagementSummaryState(
        segments=(
            AlarmManagementSummarySegmentState(
                area=AlarmManagementSummaryArea.MINE,
                group='G3',
                management_percentage=60,
                tone=AlarmManagementSummaryTone.ATTENTION,
            ),
            AlarmManagementSummarySegmentState(
                area=AlarmManagementSummaryArea.PLANT,
                group='G1',
                management_percentage=45,
                tone=AlarmManagementSummaryTone.CRITICAL,
            ),
        )
    )


def test_summary_renders_mine_and_plant_as_equal_segments() -> None:
    component = build_alarm_management_summary(_state())

    assert component is not None
    segments = [
        item
        for item in _walk(component)
        if 'ada-alarm-management-summary__segment' in (_props(item).get('className') or '')
    ]

    assert _props(component)['className'] == 'ada-alarm-management-summary'
    assert len(segments) == 2
    assert _props(segments[0])['data-area'] == 'mine'
    assert _props(segments[0])['data-tone'] == 'attention'
    assert _props(segments[1])['data-area'] == 'plant'
    assert _props(segments[1])['data-tone'] == 'critical'


def test_summary_keeps_group_and_management_labels() -> None:
    component = build_alarm_management_summary(_state())
    assert component is not None

    text = [
        str(child)
        for item in _walk(component)
        for child in (
            [getattr(item, 'children', None)]
            if isinstance(getattr(item, 'children', None), str)
            else []
        )
    ]

    assert 'Grupo Mina' in text
    assert 'G3' in text
    assert 'Gestión Mina' in text
    assert '60%' in text
    assert 'Grupo Planta' in text
    assert 'Gestión Planta' in text
    assert '45%' in text


def test_none_state_collapses_without_placeholder() -> None:
    assert build_alarm_management_summary(None) is None
