from ada.contracts.tools.enums import ToolScope
from ada.web.ui.global_indicator import (
    GlobalIndicatorDefinition,
    GlobalIndicatorMeasurementDefinition,
)

from .bindings import DashboardGlobalIndicatorBinding

# Catálogo productivo único de Global Indicators para Operaciones Integradas.
# Esta entrada de prueba permite desarrollar la composición aun cuando Delivery todavía no exista.
INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS: tuple[DashboardGlobalIndicatorBinding, ...] = (
    DashboardGlobalIndicatorBinding(
        definition=GlobalIndicatorDefinition(
            key='test_indicator',
            label='Indicador Prueba',
            unit='kt',
            measurements=(
                GlobalIndicatorMeasurementDefinition(
                    key='day',
                    label='Día',
                    actual_kpi_key='test_indicator_day_actual',
                    plan_kpi_key='test_indicator_day_plan',
                ),
                GlobalIndicatorMeasurementDefinition(
                    key='week',
                    label='Semana',
                    actual_kpi_key='test_indicator_week_actual',
                    plan_kpi_key='test_indicator_week_plan',
                ),
            ),
        ),
        scopes=(
            ToolScope.MINE,
            ToolScope.PLANT,
        ),
    ),
)
