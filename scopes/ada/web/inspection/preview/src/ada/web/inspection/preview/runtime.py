from __future__ import annotations

from dataclasses import replace
from functools import partial
from pathlib import Path
from time import sleep

from dash import Dash, Input, Output, dcc
from dash.development.base_component import Component

from ada.web.application.generic.application import create_application_definition
from ada.web.inspection.api import create_kpi_inspection_api_module
from ada.web.inspection.core import KpiDefinition, KpiDefinitionSnapshot, KpiDefinitionSnapshotStore
from ada.web.inspection.surface import create_kpi_inspection_surface_module
from ada.web.ui.global_indicator import (
    GlobalIndicatorCollection,
    GlobalIndicatorLastMeasurementState,
    GlobalIndicatorMeasurementState,
    GlobalIndicatorState,
    build_global_indicators,
)
from atlanticus.web.application import create_web_application
from atlanticus.web.models import (
    ApplicationMetadata,
    WebApplicationDefinition,
    WebApplicationRuntime,
)
from atlanticus.web.modules import WebModule
from atlanticus.web.services import ServiceRegistry

_PREVIEW_VERSION = '0.1.5'
_PREVIEW_ROOT = Path(__file__).resolve().parents[5]
_PREVIEW_INTERVAL_ID = 'kiv003-global-indicator-interval'
_PREVIEW_HOST_ID = 'kiv003-global-indicators-host'
_PREVIEW_INTERVAL_MS = 2000
_PREVIEW_API_DELAY_SECONDS = 0.75


def create_preview_snapshot() -> KpiDefinitionSnapshot:
    definitions = [
        _definition(
            'transported_shift_actual',
            'Tonelaje transportado acumulado durante el turno actual.',
            'Turno',
            'Actual',
        ),
        _definition(
            'transported_shift_plan',
            'Objetivo de tonelaje transportado para el turno actual.',
            'Turno',
            'Plan',
        ),
        _definition(
            'transported_day_actual',
            'Tonelaje transportado acumulado durante el día operacional.',
            'Día',
            'Actual',
        ),
        _definition(
            'transported_day_plan',
            'Objetivo de tonelaje transportado para el día operacional.',
            'Día',
            'Plan',
        ),
        _definition(
            'transported_latest',
            'Última medición disponible de tonelaje transportado.',
            'Última medición',
            'Actual',
        ),
        _definition(
            'recovery_shift_actual',
            'Recuperación acumulada observada durante el turno actual.',
            'Turno',
            'Actual',
        ),
        _definition(
            'recovery_shift_plan',
            'Objetivo de recuperación definido para el turno actual.',
            'Turno',
            'Plan',
        ),
        _definition(
            'recovery_day_actual',
            'Recuperación acumulada observada durante el día operacional.',
            'Día',
            'Actual',
        ),
        KpiDefinition(kpi_key='recovery_day_plan', fields={}),
        _definition(
            'recovery_latest',
            'Última medición disponible de recuperación.',
            'Última medición',
            'Actual',
        ),
        _definition(
            'mine_movement_shift_actual',
            'Movimiento mina acumulado durante el turno actual.',
            'Turno',
            'Actual',
        ),
        _definition(
            'mine_movement_shift_plan',
            'Objetivo de movimiento mina para el turno actual.',
            'Turno',
            'Plan',
        ),
        _definition(
            'mine_movement_day_actual',
            'Movimiento mina acumulado durante el día operacional.',
            'Día',
            'Actual',
        ),
        _definition(
            'mine_movement_day_plan',
            'Objetivo de movimiento mina para el día operacional.',
            'Día',
            'Plan',
        ),
    ]
    return KpiDefinitionSnapshot(definitions=tuple(definitions))


def create_preview_global_indicators(tick: int = 0) -> GlobalIndicatorCollection:
    return GlobalIndicatorCollection(
        indicators=(
            _indicator(
                key='transported_card',
                label='Transportado',
                unit='kt',
                kpi_prefix='transported',
                shift_actual=str(184 + tick % 7),
                shift_plan='180',
                day_actual=str(521 + (tick % 7) * 2),
                day_plan='540',
                latest=str(186 + tick % 7),
            ),
            _indicator(
                key='recovery_card',
                label='Recuperación',
                unit='%',
                kpi_prefix='recovery',
                shift_actual=f'{91.4 + (tick % 5) * 0.1:.1f}',
                shift_plan='92.0',
                day_actual=f'{91.8 + (tick % 5) * 0.1:.1f}',
                day_plan='92.0',
                latest=f'{91.6 + (tick % 5) * 0.1:.1f}',
            ),
            _indicator(
                key='mine_movement_card',
                label='Movimiento Mina',
                unit='kt',
                kpi_prefix='mine_movement',
                shift_actual=str(248 + tick % 9),
                shift_plan='255',
                day_actual=str(731 + (tick % 9) * 3),
                day_plan='765',
                latest=str(251 + tick % 9),
            ),
        )
    )


def create_preview_definition() -> WebApplicationDefinition:
    store = _PreviewDelayedSnapshotStore(create_preview_snapshot())
    base = create_application_definition(
        tool_display_name='KPI Inspection Preview',
        global_indicators=create_preview_global_indicators(),
    )
    return replace(
        base,
        layout=partial(_build_preview_layout, base_layout=base.layout),
        import_name='ada.web.inspection.preview',
        metadata=ApplicationMetadata(
            application_id='ada-kpi-inspection-preview',
            display_name='ADA — KPI Inspection Preview',
            version=_PREVIEW_VERSION,
        ),
        publications_root=_PREVIEW_ROOT / '.runtime' / 'publications',
        modules=(
            *base.modules,
            _create_preview_interval_module(),
            create_kpi_inspection_api_module(store),
            create_kpi_inspection_surface_module(),
        ),
    )


def create_preview_runtime() -> WebApplicationRuntime:
    return create_web_application(create_preview_definition())


class _PreviewDelayedSnapshotStore(KpiDefinitionSnapshotStore):
    def get(self, kpi_key: str) -> KpiDefinition | None:
        sleep(_PREVIEW_API_DELAY_SECONDS)
        return super().get(kpi_key)


def _build_preview_layout(
    services: ServiceRegistry,
    *,
    base_layout,
) -> Component:
    layout = base_layout(services)
    host = _find_component_by_class(layout, 'global-indicators')
    if host is None:
        raise RuntimeError('KIV-003 preview could not locate Global Indicators host')
    host.id = _PREVIEW_HOST_ID
    root_children = list(layout.children or ())
    root_children.append(
        dcc.Interval(
            id=_PREVIEW_INTERVAL_ID,
            interval=_PREVIEW_INTERVAL_MS,
            n_intervals=0,
        )
    )
    layout.children = root_children
    return layout


def _create_preview_interval_module() -> WebModule:
    def register_callbacks(app: Dash, services: ServiceRegistry) -> None:
        del services

        @app.callback(
            Output(_PREVIEW_HOST_ID, 'children'),
            Input(_PREVIEW_INTERVAL_ID, 'n_intervals'),
        )
        def refresh_global_indicators(n_intervals: int | None):
            tick = int(n_intervals or 0)
            component = build_global_indicators(collection=create_preview_global_indicators(tick))
            return list(component.children or ())

    return WebModule(
        name='kpi-inspection-preview-interval',
        register_callbacks=register_callbacks,
    )


def _find_component_by_class(component: Component, class_name: str) -> Component | None:
    classes = str(getattr(component, 'className', '') or '').split()
    if class_name in classes:
        return component
    children = getattr(component, 'children', None)
    if children is None:
        return None
    if not isinstance(children, (list, tuple)):
        children = (children,)
    for child in children:
        if not hasattr(child, 'to_plotly_json'):
            continue
        found = _find_component_by_class(child, class_name)
        if found is not None:
            return found
    return None


def _definition(kpi_key: str, description: str, window: str, value_type: str) -> KpiDefinition:
    return KpiDefinition(
        kpi_key=kpi_key,
        fields={
            'description': description,
            'window': window,
            'value_type': value_type,
            'owner': 'Operaciones',
        },
    )


def _indicator(
    *,
    key: str,
    label: str,
    unit: str,
    kpi_prefix: str,
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
                actual_kpi_key=f'{kpi_prefix}_shift_actual',
                plan_kpi_key=f'{kpi_prefix}_shift_plan',
            ),
            GlobalIndicatorMeasurementState(
                key='day',
                label='Día',
                actual_value=day_actual,
                plan_value=day_plan,
                actual_kpi_key=f'{kpi_prefix}_day_actual',
                plan_kpi_key=f'{kpi_prefix}_day_plan',
            ),
        ),
        last_measurement=GlobalIndicatorLastMeasurementState(
            actual_value=latest,
            actual_kpi_key=f'{kpi_prefix}_latest',
        ),
    )
