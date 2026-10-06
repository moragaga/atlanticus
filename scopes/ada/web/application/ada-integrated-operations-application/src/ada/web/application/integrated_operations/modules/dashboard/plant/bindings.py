from ada.contracts.tools.enums import ToolScope
from ada.web.application.integrated_operations.modules.dashboard.contracts import (
    DashboardCardBinding,
    DashboardComponentBinding,
)

STOCKPILE_CHACAY = DashboardComponentBinding(
    key='stockpile_chacay',
    label='STOCKPILE CHACAY',
    scope=ToolScope.PLANT,
    tool_component_key='cmp_stockpile_chacay_4265300400b1',
    cards=(
        DashboardCardBinding(
            key='stockpile_chacay',
            label='Stockpile Chacay',
            tool_subcomponent_key='sub_stockpile_chacay_391a0d9c56cb',
        ),
        DashboardCardBinding(
            key='tendencia_alimentado',
            label='Tendencia Alimentado',
            tool_subcomponent_key='sub_tendencia_alimentado_98a0c47facaf',
        ),
    ),
)

MOLIENDA = DashboardComponentBinding(
    key='molienda',
    label='MOLIENDA',
    scope=ToolScope.PLANT,
    tool_component_key='cmp_molienda_e3aaacbeb627',
    cards=(
        DashboardCardBinding(
            key='molienda',
            label='Molienda',
            tool_subcomponent_key='sub_molienda_a8890f24edb7',
        ),
    ),
)

FLOTACION = DashboardComponentBinding(
    key='flotacion',
    label='FLOTACIÓN',
    scope=ToolScope.PLANT,
    tool_component_key='cmp_flotacion_9bbf64c07ea7',
    cards=(
        DashboardCardBinding(
            key='colectiva',
            label='Colectiva',
            tool_subcomponent_key='sub_colectiva_1144e0368316',
        ),
        DashboardCardBinding(
            key='selectiva',
            label='Selectiva',
            tool_subcomponent_key='sub_selectiva_13ecce0283b4',
        ),
    ),
)

TRANSPORTE_FLUIDOS = DashboardComponentBinding(
    key='transporte_fluidos',
    label='TRANSPORTE DE FLUIDOS',
    scope=ToolScope.PLANT,
    tool_component_key='cmp_transporte_de_fluidos_823d86d77b46',
    cards=(
        DashboardCardBinding(
            key='str',
            label='STR',
            tool_subcomponent_key='sub_str_798d405ac5fe',
        ),
        DashboardCardBinding(
            key='stc',
            label='STC',
            tool_subcomponent_key='sub_stc_80570bfc1947',
        ),
        DashboardCardBinding(
            key='tranque',
            label='Tranque',
            tool_subcomponent_key='sub_tranque_72a1d5883f14',
        ),
        DashboardCardBinding(
            key='sta',
            label='STA',
            tool_subcomponent_key='sub_sta_f3f6b7525f63',
        ),
    ),
)

PUERTO = DashboardComponentBinding(
    key='puerto',
    label='PUERTO',
    scope=ToolScope.PLANT,
    tool_component_key='cmp_puerto_9f4e782f8c6a',
    cards=(
        DashboardCardBinding(
            key='puerto',
            label='Puerto',
            tool_subcomponent_key='sub_puerto_1671f8c4ae3f',
        ),
        DashboardCardBinding(
            key='desaladora',
            label='Desaladora',
            tool_subcomponent_key='sub_desaladora_f41f09685011',
        ),
    ),
)

PLANT_COMPONENTS = (
    STOCKPILE_CHACAY,
    MOLIENDA,
    FLOTACION,
    TRANSPORTE_FLUIDOS,
    PUERTO,
)
