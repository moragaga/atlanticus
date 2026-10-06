from __future__ import annotations

from dataclasses import dataclass

from ada.contracts.tools.enums import ToolScope


@dataclass(frozen=True, slots=True)
class DashboardCardBinding:
    # `key` identifica el slot visual y no debe confundirse con la identidad publicada por Tools.
    key: str
    label: str
    # Esta es la única identidad que debe completar el desarrollador cuando conozca el contrato real.
    tool_subcomponent_key: str | None = None


@dataclass(frozen=True, slots=True)
class DashboardComponentBinding:
    # La geometría usa una clave visual estable aunque el Tool cambie su identificador contractual.
    key: str
    label: str
    scope: ToolScope
    cards: tuple[DashboardCardBinding, ...]
    # Mantener None evita inventar una correlación no verificada con Tool Structure.
    tool_component_key: str | None = None


@dataclass(frozen=True, slots=True)
class DashboardSharedCardBinding:
    # La card compartida conserva owner y enlaces separados porque no representa un componente independiente.
    key: str
    label: str
    scope: ToolScope
    tool_component_key: str | None = None
    tool_subcomponent_key: str | None = None
    linked_tool_component_keys: tuple[str, ...] = ()


# Inventario visual de Mina basado en el layout ejecutado y en la referencia multi-stage.
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

# Cuando se conozca el Tool real, aquí se completa owner, subcomponente y linked component.
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

# Inventario visual de Planta.
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

# El orden es contractual para la geometría: cuatro slots Mina y cinco slots Planta.
MINE_COMPONENTS = (
    GENERAL_MINA,
    CARGUIO,
    TRANSPORTE,
    CHANCADO_STMG,
)

PLANT_COMPONENTS = (
    STOCKPILE_CHACAY,
    MOLIENDA,
    FLOTACION,
    TRANSPORTE_FLUIDOS,
    PUERTO,
)

DASHBOARD_COMPONENTS = (*MINE_COMPONENTS, *PLANT_COMPONENTS)
