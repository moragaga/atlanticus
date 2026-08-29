from datetime import UTC, datetime

import pytest
from dash import html
from dash.development.base_component import Component

from ada.web.ui.time_status import (
    TimeStatusDefinitionError,
    TimeStatusFreshnessPolicy,
    TimeStatusSourceCondition,
    TimeStatusSourceState,
    TimeStatusSummaryState,
    build_time_status,
    build_time_status_summary,
)


def _props(component: Component) -> dict:
    return component.to_plotly_json()['props']


def _walk(component: Component):
    yield component
    children = _props(component).get('children')
    if isinstance(children, Component):
        yield from _walk(children)
    elif isinstance(children, (list, tuple)):
        for child in children:
            if isinstance(child, Component):
                yield from _walk(child)


def _source(
    key: str,
    *,
    condition: TimeStatusSourceCondition,
    warning: int,
    stale: int,
    relative_age: str | None = 'hace más de 20 segundos',
) -> TimeStatusSourceState:
    timestamp = datetime(2026, 8, 28, 22, 0, tzinfo=UTC)
    if condition is TimeStatusSourceCondition.DATA_ERROR:
        timestamp = None
        relative_age = None
    return TimeStatusSourceState(
        key=key,
        label='PI' if key == 'pi' else 'Dispatch',
        policy=TimeStatusFreshnessPolicy(warning, stale),
        condition=condition,
        relative_age_text=relative_age,
        timestamp_utc=timestamp,
    )


def _pi_state(*, has_detail: bool = False) -> TimeStatusSummaryState:
    return TimeStatusSummaryState(
        pi=_source('pi', condition=TimeStatusSourceCondition.FRESH, warning=200, stale=300),
        has_detail=has_detail,
    )


def test_pi_only_summary_exposes_clock_marker_and_policy_metadata() -> None:
    component = build_time_status_summary(state=_pi_state())
    root = _props(component)

    assert root['data-has-dispatch'] == 'false'
    assert root['data-content-stale'] == 'false'
    pi = next(item for item in _walk(component) if _props(item).get('data-source-key') == 'pi')
    pi_props = _props(pi)
    assert pi_props['data-source-condition'] == 'fresh'
    assert pi_props['data-warning-after-seconds'] == '200'
    assert pi_props['data-stale-after-seconds'] == '300'
    assert any(
        _props(item).get('data-ada-time-status-clock') == 'true' for item in _walk(component)
    )


def test_pi_and_dispatch_are_one_summary_and_whole_set_is_detail_trigger() -> None:
    component = build_time_status_summary(
        state=TimeStatusSummaryState(
            pi=_source(
                'pi', condition=TimeStatusSourceCondition.PREVENTIVE, warning=200, stale=300
            ),
            dispatch=_source(
                'dispatch',
                condition=TimeStatusSourceCondition.FRESH,
                warning=400,
                stale=600,
            ),
            has_detail=True,
        )
    )
    root = _props(component)

    assert root['data-has-dispatch'] == 'true'
    assert root['data-ada-time-status-detail-trigger'] == 'true'
    assert (
        sum(1 for item in _walk(component) if _props(item).get('data-source-key') is not None) == 2
    )
    assert all(
        'data-ada-time-status-detail-trigger' not in _props(item)
        for item in list(_walk(component))[1:]
    )


def test_hard_stale_and_data_error_are_distinct_dom_states() -> None:
    stale = build_time_status_summary(
        state=TimeStatusSummaryState(
            pi=_source(
                'pi',
                condition=TimeStatusSourceCondition.HARD_STALE,
                warning=200,
                stale=300,
            )
        )
    )
    error = build_time_status_summary(
        state=TimeStatusSummaryState(
            pi=_source(
                'pi',
                condition=TimeStatusSourceCondition.DATA_ERROR,
                warning=200,
                stale=300,
            )
        )
    )

    assert _props(stale)['data-content-stale'] == 'true'
    assert _props(stale)['data-has-data-error'] == 'false'
    assert _props(error)['data-content-stale'] == 'false'
    assert _props(error)['data-has-data-error'] == 'true'


def test_composed_time_status_anchors_detail_as_summary_sibling() -> None:
    detail = html.Div('Injected detail', **{'data-test-detail': 'true'})
    component = build_time_status(state=_pi_state(has_detail=True), detail=detail)
    root = _props(component)
    children = root['children']

    assert root['data-ada-time-status-container'] == 'true'
    assert len(children) == 2
    assert _props(children[0])['data-component-key'] == 'time_status'
    assert _props(children[0])['data-ada-time-status-detail-trigger'] == 'true'
    surface = _props(children[1])
    assert surface['data-ada-time-status-detail-surface'] == 'true'
    assert surface['hidden'] is True
    assert surface['aria-hidden'] == 'true'
    assert surface['children'] is detail


def test_composed_time_status_without_detail_has_no_surface_or_trigger() -> None:
    component = build_time_status(state=_pi_state())
    children = _props(component)['children']

    assert len(children) == 1
    assert _props(children[0])['data-has-detail'] == 'false'
    assert 'data-ada-time-status-detail-trigger' not in _props(children[0])
    assert not any(
        _props(item).get('data-ada-time-status-detail-surface') == 'true'
        for item in _walk(component)
    )


def test_detail_content_requires_detail_enabled_in_summary_contract() -> None:
    with pytest.raises(TimeStatusDefinitionError, match='requires has_detail=True'):
        build_time_status(state=_pi_state(), detail=html.Div('Unexpected detail'))


def test_detail_enabled_summary_exposes_keyboard_button_contract_closed_by_default() -> None:
    component = build_time_status(state=_pi_state(has_detail=True), detail=html.Div('Detail'))
    root = _props(component)
    summary = _props(root['children'][0])

    assert root['data-ada-time-status-detail-open'] == 'false'
    assert summary['role'] == 'button'
    assert summary['tabIndex'] == 0
    assert summary['aria-expanded'] == 'false'


def test_summary_without_detail_does_not_enter_keyboard_interaction_contract() -> None:
    component = build_time_status(state=_pi_state())
    root = _props(component)
    summary = _props(root['children'][0])

    assert 'data-ada-time-status-detail-open' not in root
    assert 'role' not in summary
    assert 'tabIndex' not in summary
    assert 'aria-expanded' not in summary
