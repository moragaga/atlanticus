from ada.contracts.tools.enums import ToolScope
from ada.web.application.integrated_operations.modules.dashboard.contracts import (
    DashboardCardBinding,
    DashboardComponentBinding,
    DashboardSharedCardBinding,
)

GENERAL_MINA = DashboardComponentBinding(
    key='general_mina',
    label='GENERAL MINA',
    scope=ToolScope.MINE,
    tool_component_key='cmp_general_mina_6df268db211b',
    cards=(
        DashboardCardBinding(
            key='movimiento_mina',
            label='Movimiento Mina',
            tool_subcomponent_key='sub_movimiento_mina_1b6d8b556371',
        ),
        DashboardCardBinding(
            key='remanentes',
            label='Remanentes',
            tool_subcomponent_key='sub_remanentes_6e22f5763660',
        ),
        DashboardCardBinding(
            key='perforacion',
            label='Perforación',
            tool_subcomponent_key='sub_perforacion_68a7f17fd16f',
        ),
        DashboardCardBinding(
            key='mp10',
            label='MP10',
            tool_subcomponent_key='sub_mp10_7c12dfcc7294',
        ),
    ),
)

CARGUIO = DashboardComponentBinding(
    key='carguio',
    label='CARGUÍO',
    scope=ToolScope.MINE,
    tool_component_key='cmp_carguio_4cbd52aaa4b0',
    cards=(
        DashboardCardBinding(
            key='carguio_global_turno',
            label='Carguío Global • Turno',
            tool_subcomponent_key='sub_carguio_global_turno_90512312d37c',
        ),
        DashboardCardBinding(
            key='equipos_servicio',
            label='Equipos de Servicio',
            tool_subcomponent_key='sub_equipos_de_servicio_ebefaa434bb8',
        ),
    ),
)

TRANSPORTE = DashboardComponentBinding(
    key='transporte',
    label='TRANSPORTE',
    scope=ToolScope.MINE,
    tool_component_key='cmp_transporte_67b979e9ab49',
    cards=(
        DashboardCardBinding(
            key='transporte_global',
            label='Transporte Global • Turno',
            tool_subcomponent_key='sub_transporte_global_turno_ffda3898fa6f',
        ),
        DashboardCardBinding(
            key='numero_operativo',
            label='N° Operativo • Turno',
            tool_subcomponent_key='sub_n_operativo_turno_12bb6dc5796e',
        ),
        DashboardCardBinding(
            key='tiempos_y_colas',
            label='Tiempos y Colas • Turno',
            tool_subcomponent_key='sub_tiempos_y_colas_108de76a6b6e',
        ),
    ),
)

CARGUIO_TRANSPORTE = DashboardSharedCardBinding(
    key='gestion_carguio_turno',
    label='Gestión Carguío • Turno',
    scope=ToolScope.MINE,
    tool_component_key='cmp_carguio_4cbd52aaa4b0',
    tool_subcomponent_key='sub_gestion_carguio_turno_8a1701f8b1b3',
    linked_tool_component_keys=('cmp_transporte_67b979e9ab49',),
)

CHANCADO_STMG = DashboardComponentBinding(
    key='chancado_stmg',
    label='CHANCADO-STMG',
    scope=ToolScope.MINE,
    tool_component_key='cmp_chancado_stmg_abd7384135fd',
    cards=(
        DashboardCardBinding(
            key='chancado_stmg',
            label='Chancado-STMG',
            tool_subcomponent_key='sub_chancado_stmg_eaf0341c4200',
        ),
    ),
)

MINE_COMPONENTS = (
    GENERAL_MINA,
    CARGUIO,
    TRANSPORTE,
    CHANCADO_STMG,
)
