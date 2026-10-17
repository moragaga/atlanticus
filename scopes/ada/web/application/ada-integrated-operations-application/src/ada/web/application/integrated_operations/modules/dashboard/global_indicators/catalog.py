from collections.abc import Iterator

from ada.contracts.tools.enums import ToolScope
from ada.web.content_state import ContentState
from ada.web.ui.global_indicator import (
    GlobalIndicatorDefinition,
    GlobalIndicatorMeasurementDefinition,
)
from ..contracts import OperationalControlSource
from .bindings import DashboardGlobalIndicatorBinding

_DEFINITION = (
    {'label': 'Movimiento Mina', 'unit': 'ktms', 'key': 'movimiento_mina', 'scopes': (ToolScope.MINE,), 'source_keys': (OperationalControlSource.DISPATCH,)},
    {'label': 'Transportado', 'unit': 'ktms', 'key': 'transportado', 'scopes': (ToolScope.MINE, ToolScope.PLANT,), 'source_keys': (OperationalControlSource.DISPATCH, OperationalControlSource.PI)},
    {'label': 'Ley Cu', 'unit': '%', 'key': 'ley_cu', 'scopes': (ToolScope.MINE,), 'source_keys': (OperationalControlSource.DISPATCH,)},
    {'label': 'Tratamiento', 'unit': 'ktms', 'key': 'tratamiento', 'scopes': (ToolScope.PLANT,), 'source_keys': (OperationalControlSource.PI,)},
    {'label': 'Recuperación Cu', 'unit': '%', 'key': 'cu_recuperacion', 'scopes': (ToolScope.PLANT,), 'source_keys': (OperationalControlSource.PI,)},
    {'label': 'Cu Fino Producido', 'unit': 'tmf', 'key': 'cu_fino_producido', 'scopes': (ToolScope.PLANT,), 'source_keys': (OperationalControlSource.PI,)},
    {'label': 'Mo Fino Producido', 'unit': 'tmf', 'key': 'mo_fino_producido', 'scopes': (ToolScope.PLANT,), 'source_keys': (OperationalControlSource.PI,)},
    {'label': 'Mo Fino Envasado', 'unit': 'tmf', 'key': 'mo_fino_envasado', 'scopes': (ToolScope.PLANT,), 'source_keys': (OperationalControlSource.PI,)},
)


def _build_global_indicators() -> tuple[DashboardGlobalIndicatorBinding, ...]:
    return (
        DashboardGlobalIndicatorBinding(
            definition=GlobalIndicatorDefinition(
                key=indicator.get('key'),
                label=indicator.get('label'),
                unit=indicator.get('unit'),
                measurements=(
                    GlobalIndicatorMeasurementDefinition(
                        key='day',
                        label='Día',
                        actual_kpi_key=f'{indicator.get('key')}_real_dia_acc',
                        plan_kpi_key=f'{indicator.get('key')}_real_dia_plan',
                    ),
                    GlobalIndicatorMeasurementDefinition(
                        key='week',
                        label='Semana',
                        actual_kpi_key=f'{indicator.get('key')}_real_semana_acc',
                        plan_kpi_key=f'{indicator.get('key')}_real_semana_plan',
                    ),
                ),
            ),
            scopes=indicator.get('scopes'),
            source_keys=indicator.get('source_keys'),
        )
        for indicator in _DEFINITION
    )


INTEGRATED_OPERATIONS_GLOBAL_INDICATORS_CONTENT_STATE = ContentState.READY
INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS: tuple[DashboardGlobalIndicatorBinding, ...] = tuple(_build_global_indicators())
