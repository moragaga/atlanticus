# Espejo comentado: el catálogo define qué indicadores y KPI existen. El estado de madurez se
# declara una sola vez para toda la colección, no indicador por indicador ni valor por valor.
from collections.abc import Iterator

from ada.contracts.tools.enums import ToolScope
from ada.web.content_state import ContentState
from ada.web.ui.global_indicator import (
    GlobalIndicatorDefinition,
    GlobalIndicatorMeasurementDefinition,
)

from .bindings import DashboardGlobalIndicatorBinding


def _build_test() -> Iterator[DashboardGlobalIndicatorBinding]:
    # Catálogo temporal de authoring: ocho indicadores para ejercitar la distribución del header.
    for index in range(1, 9):
        if index == 1:
            scopes = (ToolScope.MINE,)
        elif index == 2:
            scopes = (ToolScope.MINE, ToolScope.PLANT)
        else:
            scopes = (ToolScope.PLANT,)
        yield DashboardGlobalIndicatorBinding(
            definition=GlobalIndicatorDefinition(
                key=f'test_indicator_{index}',
                label=f'Indicador Prueba {index}',
                unit='kt',
                measurements=(
                    GlobalIndicatorMeasurementDefinition(
                        key='day',
                        label='Día',
                        actual_kpi_key=f'test_indicator_day_actual_{index}',
                        plan_kpi_key=f'test_indicator_day_plan_{index}',
                    ),
                    GlobalIndicatorMeasurementDefinition(
                        key='week',
                        label='Semana',
                        actual_kpi_key=f'test_indicator_week_actual_{index}',
                        plan_kpi_key=f'test_indicator_week_plan_{index}',
                    ),
                ),
            ),
            scopes=scopes,
        )


# En NORMAL se presenta el overlay de toda la colección; AUTHORING lo oculta por contrato
# operacional para poder seguir diseñando el grid subyacente.
INTEGRATED_OPERATIONS_GLOBAL_INDICATORS_CONTENT_STATE = ContentState.CONSTRUCTION
INTEGRATED_OPERATIONS_GLOBAL_INDICATOR_BINDINGS: tuple[DashboardGlobalIndicatorBinding, ...] = (
    tuple(_build_test())
)
