from datetime import UTC, datetime

from dash.development.base_component import Component

from ada.web.ui.time_status import (
    TimeStatusFreshnessPolicy,
    TimeStatusSourceCondition,
    TimeStatusSourceState,
    TimeStatusSummaryState,
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


def test_pi_only_summary_exposes_clock_marker_and_policy_metadata() -> None:
    component = build_time_status_summary(
        state=TimeStatusSummaryState(
            pi=_source('pi', condition=TimeStatusSourceCondition.FRESH, warning=200, stale=300)
        )
    )
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
