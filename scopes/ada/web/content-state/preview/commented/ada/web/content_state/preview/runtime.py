# Espejo comentado del harness CS-008.
# Compone Generic Application, el bridge Content State y KPI Inspection real para validar overlays sin tocar producto.
# El preview rerenderiza únicamente Time Status; Global Indicators reacciona mediante eventos de freshness.
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

from dash import Dash, Input, Output, dcc, html
from dash.development.base_component import Component

from ada.web.alarms.management_summary import (
    AlarmManagementSummaryArea,
    AlarmManagementSummarySegmentState,
    AlarmManagementSummaryState,
    AlarmManagementSummaryTone,
)
from ada.web.alarms.status import AlarmStatusState
from ada.web.application.generic.application import create_application_definition
from ada.web.content_state.dependency_resolver import ContentStateDependency
from ada.web.inspection.api import create_kpi_inspection_api_module
from ada.web.inspection.core import KpiDefinition, KpiDefinitionSnapshot, KpiDefinitionSnapshotStore
from ada.web.inspection.surface import create_kpi_inspection_surface_module
from ada.web.ui.content_state import ContentState, build_content_state_wrapper
from ada.web.ui.global_indicator import (
    GlobalIndicatorCollection,
    GlobalIndicatorLastMeasurementState,
    GlobalIndicatorMeasurementState,
    GlobalIndicatorState,
)
from ada.web.ui.time_status import (
    TimeStatusDetailSourceState,
    TimeStatusDetailState,
    TimeStatusFreshnessPolicy,
    TimeStatusSummaryState,
    build_time_status,
    build_time_status_detail,
    resolve_time_status_source_state,
)
from atlanticus.web.application import create_web_application
from atlanticus.web.models import (
    ApplicationMetadata,
    WebApplicationDefinition,
    WebApplicationRuntime,
)
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry

_PREVIEW_VERSION = '0.1.0'
_PREVIEW_ROOT = Path(__file__).resolve().parents[5]
_PREVIEW_INTERVAL_ID = 'cs008-content-state-interval'
_PREVIEW_SCENARIO_ID = 'cs008-content-state-scenario'
_PREVIEW_SESSION_ID = 'cs008-content-state-session'
_PREVIEW_TIME_STATUS_HOST_ID = 'cs008-time-status-host'
_PREVIEW_EXPECTED_ID = 'cs008-content-state-expected'
_PREVIEW_TICK_ID = 'cs008-content-state-tick'
_PREVIEW_INTERVAL_MS = 2000
_DEFAULT_SCENARIO = 'both_fresh'
_PI_POLICY = TimeStatusFreshnessPolicy(warning_after_seconds=200, stale_after_seconds=300)
_DISPATCH_POLICY = TimeStatusFreshnessPolicy(warning_after_seconds=400, stale_after_seconds=600)
_LIVE_PI_POLICY = TimeStatusFreshnessPolicy(warning_after_seconds=6, stale_after_seconds=12)
_LIVE_DISPATCH_POLICY = TimeStatusFreshnessPolicy(warning_after_seconds=10, stale_after_seconds=16)
_TOOL_DISPLAY_NAMES = {
    'integrated_operations': 'Operaciones Integradas',
    'process': 'Procesos',
}


@dataclass(frozen=True, slots=True)
class _Scenario:
    key: str
    label: str
    expected_state: ContentState
    expected: str


_SCENARIOS = (
    _Scenario(
        key='both_fresh',
        label='01 · PI + Dispatch Fresh → READY',
        expected_state=ContentState.READY,
        expected='Global Indicators debe permanecer sin overlay. BlockGrade Error sigue siendo informativo.',
    ),
    _Scenario(
        key='pi_preventive',
        label='02 · PI Preventive + Dispatch Fresh → READY',
        expected_state=ContentState.READY,
        expected='PI puede advertir en Time Status, pero Global Indicators no debe degradarse.',
    ),
    _Scenario(
        key='pi_hard_stale',
        label='03 · PI Hard stale + Dispatch Fresh → STALE',
        expected_state=ContentState.STALE,
        expected=(
            'Global Indicators debe mostrar “Información desactualizada” aunque el Time Status global '
            'todavía no esté stale: el componente usa OR por sus propias dependencias.'
        ),
    ),
    _Scenario(
        key='dispatch_hard_stale',
        label='04 · PI Fresh + Dispatch Hard stale → STALE',
        expected_state=ContentState.STALE,
        expected='Dispatch degradado debe marcar Global Indicators como información desactualizada.',
    ),
    _Scenario(
        key='pi_data_error',
        label='05 · PI Data error + Dispatch Fresh → SOURCE_ERROR',
        expected_state=ContentState.SOURCE_ERROR,
        expected='Global Indicators debe mostrar “Fuente de datos con error”.',
    ),
    _Scenario(
        key='mixed_source_error',
        label='06 · PI Hard stale + Dispatch Data error → SOURCE_ERROR',
        expected_state=ContentState.SOURCE_ERROR,
        expected='SOURCE_ERROR debe ganar sobre STALE para el mismo componente.',
    ),
    _Scenario(
        key='both_hard_stale',
        label='07 · PI + Dispatch Hard stale → STALE',
        expected_state=ContentState.STALE,
        expected='Ambas fuentes stale mantienen un único overlay “Información desactualizada”.',
    ),
    _Scenario(
        key='live_aging',
        label='08 · Aging acelerado + rerender → READY/STALE',
        expected_state=ContentState.STALE,
        expected=(
            'PI cruza 6/12 s y Dispatch 10/16 s. Global Indicators debe pasar a STALE apenas PI '
            'llegue a hard stale, sin esperar a que ambas fuentes estén stale y sin recrear el KPI DOM.'
        ),
    ),
)
_SCENARIOS_BY_KEY = {scenario.key: scenario for scenario in _SCENARIOS}


def create_preview_definition(
    *, tool_key: str = 'integrated_operations'
) -> WebApplicationDefinition:
    normalized_tool_key = _normalize_tool_key(tool_key)
    inspection_store = KpiDefinitionSnapshotStore(create_preview_snapshot())
    now = datetime.now(UTC)
    summary, detail = create_preview_scenario_state(
        _DEFAULT_SCENARIO,
        now_utc=now,
        started_at_utc=now,
    )
    base = create_application_definition(
        tool_display_name=_TOOL_DISPLAY_NAMES[normalized_tool_key],
        global_indicators=create_preview_global_indicators(),
        content_state_dependencies=(
            ContentStateDependency(
                component_key='global_indicators',
                source_keys=('pi', 'dispatch'),
            ),
        ),
        alarm_management_summary=create_preview_alarm_management_summary(),
        alarm_status=AlarmStatusState(active_count=12, managed_count=7),
        tool_key=normalized_tool_key,
        time_status_summary=summary,
        time_status_detail=detail,
    )
    return replace(
        base,
        layout=partial(
            _build_preview_layout,
            base_layout=base.layout,
            tool_key=normalized_tool_key,
        ),
        import_name='ada.web.content_state.preview',
        metadata=ApplicationMetadata(
            application_id=f'ada-content-state-preview-{normalized_tool_key}',
            display_name=f'ADA · Content State Preview · {_TOOL_DISPLAY_NAMES[normalized_tool_key]}',
            version=_PREVIEW_VERSION,
        ),
        publications_root=_PREVIEW_ROOT / '.runtime' / 'publications',
        modules=(
            *base.modules,
            create_kpi_inspection_api_module(inspection_store),
            create_kpi_inspection_surface_module(),
            _create_preview_module(tool_key=normalized_tool_key),
        ),
    )


def create_preview_runtime(*, tool_key: str = 'integrated_operations') -> WebApplicationRuntime:
    return create_web_application(create_preview_definition(tool_key=tool_key))


def create_preview_scenario_state(
    scenario_key: str,
    *,
    now_utc: datetime,
    started_at_utc: datetime,
) -> tuple[TimeStatusSummaryState, TimeStatusDetailState]:
    scenario = _require_scenario(scenario_key)
    now = _require_utc(now_utc, field_name='now_utc')
    started_at = _require_utc(started_at_utc, field_name='started_at_utc')

    if scenario.key == 'both_fresh':
        pi = _resolve_source('pi', 'PI', _PI_POLICY, now=now, age_seconds=25)
        dispatch = _resolve_source(
            'dispatch', 'Dispatch', _DISPATCH_POLICY, now=now, age_seconds=40
        )
    elif scenario.key == 'pi_preventive':
        pi = _resolve_source('pi', 'PI', _PI_POLICY, now=now, age_seconds=240)
        dispatch = _resolve_source(
            'dispatch', 'Dispatch', _DISPATCH_POLICY, now=now, age_seconds=40
        )
    elif scenario.key == 'pi_hard_stale':
        pi = _resolve_source('pi', 'PI', _PI_POLICY, now=now, age_seconds=360)
        dispatch = _resolve_source(
            'dispatch', 'Dispatch', _DISPATCH_POLICY, now=now, age_seconds=40
        )
    elif scenario.key == 'dispatch_hard_stale':
        pi = _resolve_source('pi', 'PI', _PI_POLICY, now=now, age_seconds=25)
        dispatch = _resolve_source(
            'dispatch', 'Dispatch', _DISPATCH_POLICY, now=now, age_seconds=720
        )
    elif scenario.key == 'pi_data_error':
        pi = _resolve_source('pi', 'PI', _PI_POLICY, now=now, data_error=True)
        dispatch = _resolve_source(
            'dispatch', 'Dispatch', _DISPATCH_POLICY, now=now, age_seconds=40
        )
    elif scenario.key == 'mixed_source_error':
        pi = _resolve_source('pi', 'PI', _PI_POLICY, now=now, age_seconds=360)
        dispatch = _resolve_source(
            'dispatch', 'Dispatch', _DISPATCH_POLICY, now=now, data_error=True
        )
    elif scenario.key == 'both_hard_stale':
        pi = _resolve_source('pi', 'PI', _PI_POLICY, now=now, age_seconds=360)
        dispatch = _resolve_source(
            'dispatch', 'Dispatch', _DISPATCH_POLICY, now=now, age_seconds=720
        )
    else:
        pi = resolve_time_status_source_state(
            key='pi',
            label='PI',
            policy=_LIVE_PI_POLICY,
            timestamp_utc=started_at,
            now_utc=now,
        )
        dispatch = resolve_time_status_source_state(
            key='dispatch',
            label='Dispatch',
            policy=_LIVE_DISPATCH_POLICY,
            timestamp_utc=started_at,
            now_utc=now,
        )

    return (
        TimeStatusSummaryState(pi=pi, dispatch=dispatch, has_detail=True),
        _detail_state(),
    )


def create_preview_snapshot() -> KpiDefinitionSnapshot:
    definitions = tuple(
        _definition(kpi_key, description)
        for kpi_key, description in (
            ('preview_transported_shift_actual', 'Tonelaje transportado acumulado del turno.'),
            ('preview_transported_shift_plan', 'Plan de tonelaje transportado del turno.'),
            ('preview_transported_day_actual', 'Tonelaje transportado acumulado del día.'),
            ('preview_transported_day_plan', 'Plan de tonelaje transportado del día.'),
            ('preview_transported_latest', 'Última medición de tonelaje transportado.'),
            ('preview_recovery_shift_actual', 'Recuperación observada durante el turno.'),
            ('preview_recovery_shift_plan', 'Plan de recuperación del turno.'),
            ('preview_recovery_day_actual', 'Recuperación observada durante el día.'),
            ('preview_recovery_day_plan', 'Plan de recuperación del día.'),
            ('preview_recovery_latest', 'Última medición de recuperación.'),
            ('preview_mine_movement_shift_actual', 'Movimiento mina acumulado del turno.'),
            ('preview_mine_movement_shift_plan', 'Plan de movimiento mina del turno.'),
            ('preview_mine_movement_day_actual', 'Movimiento mina acumulado del día.'),
            ('preview_mine_movement_day_plan', 'Plan de movimiento mina del día.'),
            ('preview_mine_movement_latest', 'Última medición de movimiento mina.'),
        )
    )
    return KpiDefinitionSnapshot(definitions=definitions)


def create_preview_global_indicators(*, prefix: str = 'preview') -> GlobalIndicatorCollection:
    return GlobalIndicatorCollection(
        indicators=(
            _indicator(
                key=f'{prefix}_transported_card',
                label='Transportado',
                unit='kt',
                prefix=f'{prefix}_transported',
                shift_actual='184',
                shift_plan='180',
                day_actual='521',
                day_plan='540',
                latest='186',
            ),
            _indicator(
                key=f'{prefix}_recovery_card',
                label='Recuperación',
                unit='%',
                prefix=f'{prefix}_recovery',
                shift_actual='91.4',
                shift_plan='92.0',
                day_actual='91.8',
                day_plan='92.0',
                latest='91.6',
            ),
            _indicator(
                key=f'{prefix}_mine_movement_card',
                label='Movimiento Mina',
                unit='kt',
                prefix=f'{prefix}_mine_movement',
                shift_actual='248',
                shift_plan='255',
                day_actual='731',
                day_plan='765',
                latest='251',
            ),
        )
    )


def create_preview_alarm_management_summary() -> AlarmManagementSummaryState:
    return AlarmManagementSummaryState(
        segments=(
            AlarmManagementSummarySegmentState(
                area=AlarmManagementSummaryArea.MINE,
                group=1,
                management_percentage=72,
                tone=AlarmManagementSummaryTone.ATTENTION,
            ),
            AlarmManagementSummarySegmentState(
                area=AlarmManagementSummaryArea.PLANT,
                group=3,
                management_percentage=88,
            ),
        )
    )


def preview_scenario_options() -> tuple[dict[str, str], ...]:
    return tuple({'label': scenario.label, 'value': scenario.key} for scenario in _SCENARIOS)


def _build_preview_layout(
    services: ServiceRegistry,
    *,
    base_layout,
    tool_key: str,
) -> Component:
    layout = base_layout(services)
    time_status_host = _find_component_by_prop(layout, 'data-ada-slot-key', 'time_status')
    if time_status_host is None:
        raise RuntimeError('CS-008 preview could not locate Time Status header slot')
    time_status_host.id = _PREVIEW_TIME_STATUS_HOST_ID

    content = _find_component_by_prop(layout, 'id', 'ada-application-content')
    if content is None:
        raise RuntimeError('CS-008 preview could not locate application content')
    original_children = _children(content)
    content.children = [_build_validation_panel(tool_key), *original_children]

    root_children = _children(layout)
    root_children.extend(
        [
            dcc.Store(
                id=_PREVIEW_SESSION_ID,
                storage_type='memory',
                data=_scenario_session(_DEFAULT_SCENARIO),
            ),
            dcc.Interval(
                id=_PREVIEW_INTERVAL_ID,
                interval=_PREVIEW_INTERVAL_MS,
                n_intervals=0,
            ),
        ]
    )
    layout.children = root_children
    return layout


def _build_validation_panel(tool_key: str) -> Component:
    construction_reference = build_content_state_wrapper(
        component_key='preview_reference_component',
        state=ContentState.CONSTRUCTION,
        children=html.Div(
            className='card',
            children=html.Div(
                className='card-body',
                children=[
                    html.H3('Superficie operacional de referencia', className='h6 mb-2'),
                    html.P(
                        'Este bloque existe sólo para validar el overlay declarativo de construcción.',
                        className='mb-0',
                    ),
                ],
            ),
        ),
    )
    return html.Section(
        className='container-fluid py-3',
        children=[
            html.Div(
                className='card mb-3',
                children=html.Div(
                    className='card-body',
                    children=[
                        html.H2('CS-008 · Content State Visual Freeze', className='h5 mb-2'),
                        html.P(
                            [
                                html.Strong('Tool: '),
                                f'{_TOOL_DISPLAY_NAMES[tool_key]} ({tool_key})',
                            ],
                            className='mb-2',
                        ),
                        html.P(
                            'Global Indicators depende de PI + Dispatch. El dropdown sólo rerenderiza '
                            'Time Status; el overlay del componente debe cambiar mediante el bridge CS-005. '
                            'Los valores KPI mantienen KPI Inspection real para validar clicks bajo el overlay.',
                            className='mb-3',
                        ),
                        dcc.Dropdown(
                            id=_PREVIEW_SCENARIO_ID,
                            options=list(preview_scenario_options()),
                            value=_DEFAULT_SCENARIO,
                            clearable=False,
                            searchable=False,
                        ),
                        html.P(id=_PREVIEW_EXPECTED_ID, className='mt-3 mb-1'),
                        html.Small(id=_PREVIEW_TICK_ID, className='text-body-secondary'),
                    ],
                ),
            ),
            html.Div(
                className='mb-2 fw-semibold',
                children='Referencia estática · CONSTRUCTION',
            ),
            construction_reference,
        ],
    )


def _create_preview_module(*, tool_key: str) -> WebModule:
    def register_callbacks(app: Dash, services: ServiceRegistry) -> None:
        del services

        @app.callback(Output(_PREVIEW_SESSION_ID, 'data'), Input(_PREVIEW_SCENARIO_ID, 'value'))
        def reset_scenario(scenario_key: str | None):
            return _scenario_session(str(scenario_key or _DEFAULT_SCENARIO))

        @app.callback(
            Output(_PREVIEW_TIME_STATUS_HOST_ID, 'children'),
            Output(_PREVIEW_EXPECTED_ID, 'children'),
            Output(_PREVIEW_TICK_ID, 'children'),
            Input(_PREVIEW_SESSION_ID, 'data'),
            Input(_PREVIEW_INTERVAL_ID, 'n_intervals'),
        )
        def refresh_time_status(session: dict | None, n_intervals: int | None):
            payload = session or _scenario_session(_DEFAULT_SCENARIO)
            scenario_key = str(payload.get('scenario') or _DEFAULT_SCENARIO)
            started_at = _parse_utc(str(payload.get('started_at_utc') or ''))
            now = datetime.now(UTC)
            summary, detail = create_preview_scenario_state(
                scenario_key,
                now_utc=now,
                started_at_utc=started_at,
            )
            component = build_time_status(
                tool_key=tool_key,
                state=summary,
                detail=build_time_status_detail(state=detail),
            )
            scenario = _require_scenario(scenario_key)
            tick = int(n_intervals or 0)
            expected = (
                f'Esperado objetivo: {scenario.expected_state.value.upper()} · {scenario.expected}'
            )
            return [component], expected, f'Render #{tick} · Intervalo 2 s'

    return WebModule(
        name='content-state-visual-preview-controls',
        register_callbacks=register_callbacks,
    )


def _resolve_source(
    key: str,
    label: str,
    policy: TimeStatusFreshnessPolicy,
    *,
    now: datetime,
    age_seconds: int = 0,
    data_error: bool = False,
):
    timestamp = None if data_error else now - timedelta(seconds=age_seconds)
    return resolve_time_status_source_state(
        key=key,
        label=label,
        policy=policy,
        timestamp_utc=timestamp,
        now_utc=now,
    )


def _detail_state() -> TimeStatusDetailState:
    return TimeStatusDetailState(
        sources=(
            TimeStatusDetailSourceState(
                key='blockgrade',
                label='BlockGrade',
                value='Error',
            ),
        )
    )


def _definition(kpi_key: str, description: str) -> KpiDefinition:
    return KpiDefinition(
        kpi_key=kpi_key,
        fields={
            'description': description,
            'owner': 'Operaciones',
            'preview': 'CS-008',
        },
    )


def _indicator(
    *,
    key: str,
    label: str,
    unit: str,
    prefix: str,
    shift_actual: str,
    shift_plan: str,
    day_actual: str,
    day_plan: str,
    latest: str,
) -> GlobalIndicatorState:
    return GlobalIndicatorState(
        key=key,
        label=label,
        unit=unit,
        measurements=(
            GlobalIndicatorMeasurementState(
                key='shift',
                label='Turno',
                actual_value=shift_actual,
                plan_value=shift_plan,
                actual_kpi_key=f'{prefix}_shift_actual',
                plan_kpi_key=f'{prefix}_shift_plan',
            ),
            GlobalIndicatorMeasurementState(
                key='day',
                label='Día',
                actual_value=day_actual,
                plan_value=day_plan,
                actual_kpi_key=f'{prefix}_day_actual',
                plan_kpi_key=f'{prefix}_day_plan',
            ),
        ),
        last_measurement=GlobalIndicatorLastMeasurementState(
            actual_value=latest,
            actual_kpi_key=f'{prefix}_latest',
        ),
    )


def _scenario_session(scenario_key: str) -> dict[str, str]:
    scenario = _require_scenario(scenario_key)
    return {
        'scenario': scenario.key,
        'started_at_utc': _utc_iso(datetime.now(UTC)),
    }


def _normalize_tool_key(tool_key: str) -> str:
    normalized = tool_key.strip()
    if normalized not in _TOOL_DISPLAY_NAMES:
        valid = ', '.join(_TOOL_DISPLAY_NAMES)
        raise ValueError(f'Unsupported preview tool_key: {normalized!r}. Expected one of: {valid}')
    return normalized


def _require_scenario(scenario_key: str) -> _Scenario:
    scenario = _SCENARIOS_BY_KEY.get(scenario_key)
    if scenario is None:
        raise ValueError(f'Unknown Content State preview scenario: {scenario_key!r}')
    return scenario


def _require_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f'{field_name} must be timezone-aware')
    return value.astimezone(UTC)


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('Invalid preview started_at_utc') from error
    return _require_utc(parsed, field_name='started_at_utc')


def _utc_iso(value: datetime) -> str:
    return _require_utc(value, field_name='value').isoformat().replace('+00:00', 'Z')


def _children(component: Component) -> list:
    children = getattr(component, 'children', None)
    if children is None:
        return []
    if isinstance(children, (list, tuple)):
        return list(children)
    return [children]


def _find_component_by_prop(component: Component, property_name: str, value) -> Component | None:
    props = component.to_plotly_json().get('props', {})
    if props.get(property_name) == value:
        return component
    for child in _children(component):
        if not hasattr(child, 'to_plotly_json'):
            continue
        found = _find_component_by_prop(child, property_name, value)
        if found is not None:
            return found
    return None
