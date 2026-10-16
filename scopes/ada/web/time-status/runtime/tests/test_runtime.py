from __future__ import annotations

from datetime import UTC, datetime, timedelta

from dash.exceptions import PreventUpdate

import pytest

from ada.contracts.tools.sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceConsumptionValidationError,
    ToolSourceOperationalParticipation,
    ToolSourceOperationalParticipationValidationError,
)
from ada.web.kpis.collector import system_kpi_store_id
from ada.web.time_status.runtime import (
    TIME_STATUS_DESTINATION_KEY,
    TIME_STATUS_RUNTIME_HOST_TYPE,
    TimeStatusRuntimeBinding,
    build_time_status_runtime_component,
    build_time_status_runtime_host,
    create_time_status_runtime_module,
    resolve_time_status_summary,
    time_status_runtime_host_id,
)
from ada.web.ui.time_status import (
    TimeStatusDetailSourceState,
    TimeStatusDetailState,
    TimeStatusSourceCondition,
)

_NOW = datetime(2026, 10, 6, 22, 0, tzinfo=UTC)


class DashStub:
    def __init__(self) -> None:
        self.callback_function = None
        self.callback_args = ()

    def callback(self, *args, **_kwargs):
        self.callback_args = args

        def register(function):
            self.callback_function = function
            return function

        return register


def _binding(*, with_dispatch: bool = False, detail: TimeStatusDetailState | None = None):
    source_keys = ['pi']
    controls = [SourceControlPolicy('pi', 200, 300)]
    additional = ()
    if with_dispatch:
        source_keys.append('dispatch')
        controls.append(SourceControlPolicy('dispatch', 400, 600))
    if detail is not None:
        source_keys.extend(source.key for source in detail.sources)
        additional = tuple(source.key for source in detail.sources)
    return TimeStatusRuntimeBinding(
        consumption=ToolSourceConsumption('process', tuple(source_keys)),
        participation=ToolSourceOperationalParticipation(
            'process',
            control_sources=tuple(controls),
            additional_observation_source_keys=additional,
        ),
        detail=detail,
    )


def _store(values: dict[str, object], *, tool_key: str = 'process', destination='time_status'):
    return {
        'tool_key': tool_key,
        'destination_key': destination,
        'latest': {'manifest': {'revision': 'r1'}, 'values': values},
        'timeseries': None,
    }


def _ok(timestamp: datetime):
    value = timestamp.isoformat().replace('+00:00', 'Z')
    return {
        'status': 'ok',
        'value_kind': 'value',
        'value_type': 'text',
        'value': value,
        'parsed_value': value,
    }


def test_pi_only_binding_is_valid_and_dispatch_is_absent() -> None:
    binding = _binding()
    summary = resolve_time_status_summary(
        _store({'pi_last_update': _ok(_NOW - timedelta(seconds=10))}),
        binding=binding,
        now_utc=_NOW,
    )

    assert summary.pi.condition is TimeStatusSourceCondition.FRESH
    assert summary.dispatch is None
    assert summary.has_detail is True


def test_pi_and_dispatch_use_independent_control_thresholds() -> None:
    summary = resolve_time_status_summary(
        _store(
            {
                'pi_last_update': _ok(_NOW - timedelta(seconds=250)),
                'dispatch_last_update': _ok(_NOW - timedelta(seconds=450)),
            }
        ),
        binding=_binding(with_dispatch=True),
        now_utc=_NOW,
    )

    assert summary.pi.condition is TimeStatusSourceCondition.PREVENTIVE
    assert summary.dispatch is not None
    assert summary.dispatch.condition is TimeStatusSourceCondition.PREVENTIVE
    assert summary.pi.key == 'pi'
    assert summary.dispatch.key == 'dispatch'
    assert summary.pi.timestamp_utc == _NOW - timedelta(seconds=250)
    assert summary.dispatch.timestamp_utc == _NOW - timedelta(seconds=450)
    assert summary.pi.policy.warning_after_seconds == 200
    assert summary.dispatch.policy.warning_after_seconds == 400


def test_configured_dispatch_missing_from_store_is_data_error() -> None:
    summary = resolve_time_status_summary(
        _store({'pi_last_update': _ok(_NOW)}),
        binding=_binding(with_dispatch=True),
        now_utc=_NOW,
    )

    assert summary.dispatch is not None
    assert summary.dispatch.condition is TimeStatusSourceCondition.DATA_ERROR


@pytest.mark.parametrize(
    'entry',
    [
        {
            'status': 'missing', 'value_kind': None, 'value_type': None,
            'value': None, 'parsed_value': None,
        },
        {
            'status': 'error', 'value_kind': 'value', 'value_type': 'text',
            'value': None, 'parsed_value': None,
        },
        {
            'status': 'ok', 'value_kind': 'json', 'value_type': None,
            'value': {'timestamp': '2026-10-06T22:00:00Z'}, 'parsed_value': None,
        },
        {
            'status': 'ok', 'value_kind': 'value', 'value_type': 'text',
            'value': 'not-a-timestamp', 'parsed_value': 'not-a-timestamp',
        },
        {
            'status': 'ok', 'value_kind': 'value', 'value_type': 'text',
            'value': '2026-10-06T22:00:00', 'parsed_value': '2026-10-06T22:00:00',
        },
    ],
)
def test_degraded_or_invalid_pi_value_becomes_data_error(entry: dict[str, object]) -> None:
    summary = resolve_time_status_summary(
        _store({'pi_last_update': entry}),
        binding=_binding(),
        now_utc=_NOW,
    )

    assert summary.pi.condition is TimeStatusSourceCondition.DATA_ERROR


def test_legacy_control_keys_are_not_timestamp_kpi_aliases() -> None:
    summary = resolve_time_status_summary(
        _store({'pi': _ok(_NOW), 'dispatch': _ok(_NOW)}),
        binding=_binding(with_dispatch=True),
        now_utc=_NOW,
    )

    assert summary.pi.condition is TimeStatusSourceCondition.DATA_ERROR
    assert summary.dispatch is not None
    assert summary.dispatch.condition is TimeStatusSourceCondition.DATA_ERROR


@pytest.mark.parametrize(
    'store',
    [
        None,
        {},
        _store({'pi_last_update': _ok(_NOW)}, tool_key='other'),
        _store({'pi_last_update': _ok(_NOW)}, destination='global_indicators'),
        {'tool_key': 'process', 'destination_key': 'time_status', 'latest': None},
    ],
)
def test_missing_or_wrong_system_store_degrades_without_raising(store: object) -> None:
    summary = resolve_time_status_summary(store, binding=_binding(), now_utc=_NOW)

    assert summary.pi.condition is TimeStatusSourceCondition.DATA_ERROR


def test_valid_old_timestamp_is_hard_stale_not_data_error() -> None:
    summary = resolve_time_status_summary(
        _store({'pi_last_update': _ok(_NOW - timedelta(seconds=360))}),
        binding=_binding(),
        now_utc=_NOW,
    )

    assert summary.pi.condition is TimeStatusSourceCondition.HARD_STALE


def test_binding_requires_pi_and_rejects_other_control_sources() -> None:
    with pytest.raises(ToolSourceConsumptionValidationError, match="Configuration: 'pi'"):
        TimeStatusRuntimeBinding(
            consumption=ToolSourceConsumption('process', ('blockgrade',)),
            participation=ToolSourceOperationalParticipation('process'),
        )

    with pytest.raises(
        ToolSourceOperationalParticipationValidationError, match='only PI and Dispatch'
    ):
        TimeStatusRuntimeBinding(
            consumption=ToolSourceConsumption('process', ('pi', 'blockgrade')),
            participation=ToolSourceOperationalParticipation(
                'process',
                control_sources=(
                    SourceControlPolicy('pi', 200, 300),
                    SourceControlPolicy('blockgrade', 400, 600),
                ),
            ),
        )


def test_consumed_dispatch_must_be_control_but_is_not_required_when_absent() -> None:
    assert _binding().participation.controls('dispatch') is False

    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='Dispatch declared by Tool Source Consumption must participate as CONTROL',
    ):
        TimeStatusRuntimeBinding(
            consumption=ToolSourceConsumption('process', ('pi', 'dispatch')),
            participation=ToolSourceOperationalParticipation(
                'process',
                control_sources=(SourceControlPolicy('pi', 200, 300),),
                additional_observation_source_keys=('dispatch',),
            ),
        )


def test_detail_sources_remain_additional_observation_only() -> None:
    detail = TimeStatusDetailState(
        sources=(TimeStatusDetailSourceState('blockgrade', 'BlockGrade', 'Error'),)
    )
    binding = _binding(detail=detail)

    assert binding.detail is detail

    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='ADDITIONAL OBSERVATION',
    ):
        TimeStatusRuntimeBinding(
            consumption=ToolSourceConsumption('process', ('pi', 'blockgrade')),
            participation=ToolSourceOperationalParticipation(
                'process',
                control_sources=(SourceControlPolicy('pi', 200, 300),),
            ),
            detail=detail,
        )


def test_runtime_host_starts_as_data_error_and_keeps_stable_identity() -> None:
    host = build_time_status_runtime_host(_binding())
    props = host.to_plotly_json()['props']

    assert props['id'] == {
        'type': TIME_STATUS_RUNTIME_HOST_TYPE,
        'tool': 'process',
    }
    assert props['data-ada-time-status-runtime-host'] == 'true'
    assert props['data-ready'] == 'false'
    child = props['children']
    child_props = child.to_plotly_json()['props']
    assert child_props['data-ada-time-status-tool-key'] == 'process'


def test_runtime_component_renders_detail_without_own_polling() -> None:
    detail = TimeStatusDetailState(
        sources=(TimeStatusDetailSourceState('blockgrade', 'BlockGrade', 'Error'),)
    )
    component = build_time_status_runtime_component(
        _store({'pi_last_update': _ok(_NOW)}),
        binding=_binding(detail=detail),
        now_utc=_NOW,
    )
    props = component.to_plotly_json()['props']

    assert props['data-ada-time-status-tool-key'] == 'process'
    assert len(props['children']) == 2


def test_runtime_module_bridges_exact_collector_system_store_to_host() -> None:
    binding = _binding()
    module = create_time_status_runtime_module(binding)

    assert module.name == 'ada-time-status-runtime'
    assert time_status_runtime_host_id('process') == {
        'type': TIME_STATUS_RUNTIME_HOST_TYPE,
        'tool': 'process',
    }
    assert system_kpi_store_id('process', TIME_STATUS_DESTINATION_KEY) == {
        'type': 'ada-kpi-system-store',
        'tool': 'process',
        'destination': 'time_status',
    }


def _walk(component):
    yield component
    children = component.to_plotly_json()['props'].get('children')
    if hasattr(children, 'to_plotly_json'):
        yield from _walk(children)
    elif isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, 'to_plotly_json'):
                yield from _walk(child)


def test_runtime_callback_consumes_browser_system_store_without_polling() -> None:
    binding = _binding()
    module = create_time_status_runtime_module(binding)
    dash_app = DashStub()
    module.register_callbacks(dash_app, object())

    with pytest.raises(PreventUpdate):
        dash_app.callback_function(None, _store({'pi_last_update': _ok(_NOW)}))
    rendered, ready = dash_app.callback_function(
        {'initial_latest_state': 'ready'},
        _store({'pi_last_update': _ok(_NOW)}),
    )
    assert ready == 'true'

    source = next(
        component
        for component in _walk(rendered)
        if component.to_plotly_json()['props'].get('data-source-key') == 'pi'
    )

    assert source.to_plotly_json()['props']['data-source-timestamp-utc'] == '2026-10-06T22:00:00Z'
    assert dash_app.callback_args


def test_runtime_detail_uses_existing_pi_timestamp_without_dispatch() -> None:
    rendered = build_time_status_runtime_component(
        _store({'pi_last_update': _ok(_NOW)}),
        binding=_binding(), now_utc=_NOW,
    )
    rows = [
        node.to_plotly_json()['props'] for node in _walk(rendered)
        if node.to_plotly_json()['props'].get('data-ada-time-status-detail-control') == 'true'
    ]
    assert [row['data-source-key'] for row in rows] == ['pi']
    assert rows[0]['children'][1].to_plotly_json()['props'][
        'data-ada-time-status-detail-timestamp-utc'
    ] == '2026-10-06T22:00:00Z'


def test_runtime_detail_marks_missing_dispatch_and_keeps_extra_source() -> None:
    detail = TimeStatusDetailState(
        sources=(TimeStatusDetailSourceState('blockgrade', 'BlockGrade', 'Observado'),)
    )
    rendered = build_time_status_runtime_component(
        _store({'pi_last_update': _ok(_NOW)}),
        binding=_binding(with_dispatch=True, detail=detail),
        now_utc=_NOW,
    )
    rows = [
        node.to_plotly_json()['props'] for node in _walk(rendered)
        if node.to_plotly_json()['props'].get('data-source-role') in {'control', 'informational'}
    ]
    assert [(row['data-source-key'], row['data-source-role']) for row in rows] == [
        ('pi', 'control'), ('dispatch', 'control'), ('blockgrade', 'informational'),
    ]
    invalid = rows[1]['children'][1].to_plotly_json()['props']
    assert invalid['data-ada-time-status-detail-timestamp-utc'] == ''
    assert invalid['children'] == 'Sin información temporal disponible'


def test_time_status_renders_degraded_content_without_latest():
    dash_app = DashStub()
    create_time_status_runtime_module(_binding()).register_callbacks(dash_app, object())
    _, ready = dash_app.callback_function({'initial_latest_state': 'empty'}, None)
    assert ready == 'true'
