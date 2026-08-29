from __future__ import annotations

from datetime import UTC, datetime

from dash import Dash, Input, Output, dcc, html

from ada.web.ui.time_status import (
    TimeStatusFreshnessPolicy,
    TimeStatusSourceCondition,
    TimeStatusSourceState,
    TimeStatusSummaryState,
    build_time_status,
)

_INTERVAL_ID = 'ts007-interval'
_HOST_ID = 'ts007-time-status-host'
_TOOL_KEY = 'process'


def _state(tick: int) -> TimeStatusSummaryState:
    return TimeStatusSummaryState(
        pi=TimeStatusSourceState(
            key='pi',
            label='PI',
            policy=TimeStatusFreshnessPolicy(200, 300),
            condition=TimeStatusSourceCondition.FRESH,
            relative_age_text=f'hace más de {20 + tick} segundos',
            timestamp_utc=datetime(2026, 8, 29, 21, 0, tick, tzinfo=UTC),
        ),
        has_detail=True,
    )


def _render(tick: int):
    return build_time_status(
        tool_key=_TOOL_KEY,
        state=_state(tick),
        detail=html.Div(f'Detail tick {tick}', **{'data-test-detail-tick': str(tick)}),
    )


def _props(component):
    return component.to_plotly_json()['props']


def _build_interval_app() -> tuple[Dash, object]:
    app = Dash(__name__)
    app.layout = html.Div(
        [
            dcc.Interval(id=_INTERVAL_ID, interval=250, n_intervals=0),
            html.Div(_render(0), id=_HOST_ID),
        ]
    )

    @app.callback(Output(_HOST_ID, 'children'), Input(_INTERVAL_ID, 'n_intervals'))
    def refresh_time_status(n_intervals: int | None):
        return _render(int(n_intervals or 0))

    return app, refresh_time_status


def test_interval_harness_replaces_only_time_status_host_children() -> None:
    app, _refresh = _build_interval_app()
    interval, host = app.layout.children

    assert interval.__class__.__name__ == 'Interval'
    assert interval.id == _INTERVAL_ID
    assert interval.interval == 250
    assert host.id == _HOST_ID
    assert any(f'{_HOST_ID}.children' in output for output in app.callback_map)


def test_interval_renders_keep_tool_identity_while_replacing_summary_and_detail() -> None:
    _app, refresh = _build_interval_app()
    renders = [refresh(tick) for tick in range(4)]

    assert len({id(component) for component in renders}) == 4
    assert [_props(component)['data-ada-time-status-tool-key'] for component in renders] == [
        _TOOL_KEY
    ] * 4
    assert [_props(component)['data-ada-time-status-detail-open'] for component in renders] == [
        'false'
    ] * 4


def test_interval_callback_does_not_own_client_open_state() -> None:
    app, _refresh = _build_interval_app()
    callback_outputs = tuple(app.callback_map)

    assert callback_outputs
    assert all('data-ada-time-status-detail-open' not in output for output in callback_outputs)
    assert all('aria-expanded' not in output for output in callback_outputs)


def test_interval_renders_update_detail_content_without_changing_tool_scope() -> None:
    _app, refresh = _build_interval_app()
    renders = [refresh(tick) for tick in range(3)]
    details = []
    for component in renders:
        surface = _props(component)['children'][1]
        detail = _props(surface)['children']
        details.append(
            (_props(component)['data-ada-time-status-tool-key'], _props(detail)['children'])
        )

    assert details == [
        (_TOOL_KEY, 'Detail tick 0'),
        (_TOOL_KEY, 'Detail tick 1'),
        (_TOOL_KEY, 'Detail tick 2'),
    ]
