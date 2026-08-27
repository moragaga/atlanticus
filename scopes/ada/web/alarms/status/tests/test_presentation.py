from dash.development.base_component import Component

from ada.web.alarms.status import AlarmStatusState, build_alarm_status


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


def test_alarm_status_renders_active_and_managed_as_actions() -> None:
    component = build_alarm_status(AlarmStatusState(active_count=3, managed_count=2))

    assert component is not None
    actions = [
        item
        for item in _walk(component)
        if 'ada-alarm-status__action' in (_props(item).get('className') or '')
    ]

    assert _props(component)['className'] == 'ada-alarm-status'
    assert len(actions) == 2
    assert _props(actions[0])['data-alarm-status-action'] == 'active'
    assert _props(actions[0])['type'] == 'button'
    assert _props(actions[1])['data-alarm-status-action'] == 'managed'
    assert _props(actions[1])['type'] == 'button'


def test_alarm_status_keeps_counts_and_labels() -> None:
    component = build_alarm_status(AlarmStatusState(active_count=12, managed_count=7))
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

    assert 'Alarmas' in text
    assert '12' in text
    assert 'Activas' in text
    assert '7' in text
    assert 'Gestionadas' in text


def test_none_state_collapses_without_placeholder() -> None:
    assert build_alarm_status(None) is None


def test_alarm_status_label_uses_bell_icon() -> None:
    component = build_alarm_status(AlarmStatusState(active_count=4, managed_count=3))
    assert component is not None

    icons = [
        item
        for item in _walk(component)
        if 'ada-alarm-status__icon' in (_props(item).get('className') or '')
    ]

    assert len(icons) == 1
    classes = _props(icons[0])['className'].split()
    assert 'bi' in classes
    assert 'bi-bell-fill' in classes
    assert _props(icons[0])['aria-hidden'] == 'true'
