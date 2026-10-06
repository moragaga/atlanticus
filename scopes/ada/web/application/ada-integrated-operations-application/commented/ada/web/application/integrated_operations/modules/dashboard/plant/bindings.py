from ada.contracts.tools.enums import ToolScope
from ada.web.application.integrated_operations.modules.dashboard.contracts import (
    DashboardCardBinding,
    DashboardComponentBinding,
)

# Planta es dueña de su inventario visual; la raíz Dashboard no declara estos componentes.
STOCKPILE_CHACAY = DashboardComponentBinding(
    key='stockpile_chacay',
    label='STOCKPILE CHACAY',
    scope=ToolScope.PLANT,
    cards=(
        DashboardCardBinding(key='stockpile_chacay', label='Stockpile Chacay'),
        DashboardCardBinding(key='tendencia_alimentado', label='Tendencia Alimentado'),
    ),
)

MOLIENDA = DashboardComponentBinding(
    key='molienda',
    label='MOLIENDA',
    scope=ToolScope.PLANT,
    cards=(
        DashboardCardBinding(key='molienda', label='Molienda'),
    ),
)

FLOTACION = DashboardComponentBinding(
    key='flotacion',
    label='FLOTACIÓN',
    scope=ToolScope.PLANT,
    cards=(
        DashboardCardBinding(key='colectiva', label='Colectiva'),
        DashboardCardBinding(key='selectiva', label='Selectiva'),
    ),
)

TRANSPORTE_FLUIDOS = DashboardComponentBinding(
    key='transporte_fluidos',
    label='TRANSPORTE DE FLUIDOS',
    scope=ToolScope.PLANT,
    cards=(
        DashboardCardBinding(key='str', label='STR'),
        DashboardCardBinding(key='stc', label='STC'),
        DashboardCardBinding(key='tranque', label='Tranque'),
        DashboardCardBinding(key='sta', label='STA'),
    ),
)

PUERTO = DashboardComponentBinding(
    key='puerto',
    label='PUERTO',
    scope=ToolScope.PLANT,
    cards=(
        DashboardCardBinding(key='puerto', label='Puerto'),
        DashboardCardBinding(key='desaladora', label='Desaladora'),
    ),
)

# Esta colección expone sólo los componentes propios de Planta para composición o validación.
PLANT_COMPONENTS = (
    STOCKPILE_CHACAY,
    MOLIENDA,
    FLOTACION,
    TRANSPORTE_FLUIDOS,
    PUERTO,
)
