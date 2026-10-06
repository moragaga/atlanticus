from ada.contracts.tools.enums import ToolScope
from ada.web.application.integrated_operations.modules.dashboard.contracts import (
    DashboardCardBinding,
    DashboardComponentBinding,
    DashboardSharedCardBinding,
)

# Mina es dueña de su inventario visual; la raíz Dashboard no declara estos componentes.
GENERAL_MINA = DashboardComponentBinding(
    key='general_mina',
    label='GENERAL MINA',
    scope=ToolScope.MINE,
    cards=(
        DashboardCardBinding(key='movimiento_mina', label='Movimiento Mina'),
        DashboardCardBinding(key='remanentes', label='Remanentes'),
        DashboardCardBinding(key='perforacion', label='Perforación'),
        DashboardCardBinding(key='mp10', label='MP10'),
    ),
)

CARGUIO = DashboardComponentBinding(
    key='carguio',
    label='CARGUÍO',
    scope=ToolScope.MINE,
    cards=(
        DashboardCardBinding(key='equipos_servicio', label='Equipos de Servicio'),
        DashboardCardBinding(key='mezcla_hacia_chancado', label='Mezcla hacia Chancado'),
    ),
)

TRANSPORTE = DashboardComponentBinding(
    key='transporte',
    label='TRANSPORTE',
    scope=ToolScope.MINE,
    cards=(
        DashboardCardBinding(key='transporte_global', label='Transporte Global • Turno'),
        DashboardCardBinding(key='numero_operativo', label='N° Operativo • Turno'),
        DashboardCardBinding(key='tiempos_y_colas', label='Tiempos y Colas • Turno'),
    ),
)

CARGUIO_TRANSPORTE = DashboardSharedCardBinding(
    key='gestion_carguio_turno',
    label='Gestión Carguío • Turno',
    scope=ToolScope.MINE,
)

CHANCADO_STMG = DashboardComponentBinding(
    key='chancado_stmg',
    label='CHANCADO-STMG',
    scope=ToolScope.MINE,
    cards=(
        DashboardCardBinding(key='chancado_stmg', label='Chancado-STMG'),
    ),
)

# Esta colección expone sólo los componentes propios de Mina para composición o validación.
MINE_COMPONENTS = (
    GENERAL_MINA,
    CARGUIO,
    TRANSPORTE,
    CHANCADO_STMG,
)
