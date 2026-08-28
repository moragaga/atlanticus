from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ada.web.application.generic.application import create_application_definition
from ada.web.inspection.api import create_kpi_inspection_api_module
from ada.web.inspection.core import KpiDefinition, KpiDefinitionSnapshot, KpiDefinitionSnapshotStore
from ada.web.inspection.surface import create_kpi_inspection_surface_module
from ada.web.ui.global_indicator import (
    GlobalIndicatorCollection,
    GlobalIndicatorLastMeasurementState,
    GlobalIndicatorMeasurementState,
    GlobalIndicatorState,
)
from atlanticus.web.application import create_web_application
from atlanticus.web.models import (
    ApplicationMetadata,
    WebApplicationDefinition,
    WebApplicationRuntime,
)

_PREVIEW_VERSION = '0.1.2'
_PREVIEW_ROOT = Path(__file__).resolve().parents[5]


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


def create_preview_global_indicators() -> GlobalIndicatorCollection:
    return GlobalIndicatorCollection(
        indicators=(
            _indicator(
                key='transported_card',
                label='Transportado',
                unit='kt',
                kpi_prefix='transported',
                shift_actual='184',
                shift_plan='180',
                day_actual='521',
                day_plan='540',
                latest='186',
            ),
            _indicator(
                key='recovery_card',
                label='Recuperación',
                unit='%',
                kpi_prefix='recovery',
                shift_actual='91.4',
                shift_plan='92.0',
                day_actual='91.8',
                day_plan='92.0',
                latest='91.6',
            ),
            _indicator(
                key='mine_movement_card',
                label='Movimiento Mina',
                unit='kt',
                kpi_prefix='mine_movement',
                shift_actual='248',
                shift_plan='255',
                day_actual='731',
                day_plan='765',
                latest='251',
            ),
        )
    )


def create_preview_definition() -> WebApplicationDefinition:
    store = KpiDefinitionSnapshotStore(create_preview_snapshot())
    base = create_application_definition(
        tool_display_name='KPI Inspection Preview',
        global_indicators=create_preview_global_indicators(),
    )
    return replace(
        base,
        import_name='ada.web.inspection.preview',
        metadata=ApplicationMetadata(
            application_id='ada-kpi-inspection-preview',
            display_name='ADA — KPI Inspection Preview',
            version=_PREVIEW_VERSION,
        ),
        publications_root=_PREVIEW_ROOT / '.runtime' / 'publications',
        modules=(
            *base.modules,
            create_kpi_inspection_api_module(store),
            create_kpi_inspection_surface_module(),
        ),
    )


def create_preview_runtime() -> WebApplicationRuntime:
    return create_web_application(create_preview_definition())


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
