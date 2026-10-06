from ada.contracts.tools.enums import ToolScope
from ada.web.application.integrated_operations.modules.dashboard.card import (
    build_component_panel,
    build_shared_dashboard_card,
)
from ada.web.application.integrated_operations.modules.dashboard.contracts import (
    DashboardCardBinding,
    DashboardComponentBinding,
    DashboardSharedCardBinding,
)
from ada.web.application.integrated_operations.modules.dashboard.layout import (
    build_dashboard_layout,
)
from ada.web.application.integrated_operations.modules.dashboard.mine import (
    CARGUIO_TRANSPORTE,
    MINE_COMPONENTS,
)
from ada.web.application.integrated_operations.modules.dashboard.plant import (
    PLANT_COMPONENTS,
)


def _props(component):
    return component.to_plotly_json()['props']


def _walk(component):
    yield component
    children = _props(component).get('children')
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = (children,)
    for child in children:
        if hasattr(child, 'to_plotly_json'):
            yield from _walk(child)


def _has_class(component, class_name: str) -> bool:
    return class_name in str(_props(component).get('className', '')).split()


def test_dashboard_declares_complete_visual_card_inventory_by_scope() -> None:
    mine_card_keys = [card.key for component in MINE_COMPONENTS for card in component.cards]
    mine_card_keys.append(CARGUIO_TRANSPORTE.key)
    plant_card_keys = [card.key for component in PLANT_COMPONENTS for card in component.cards]
    card_keys = [*mine_card_keys, *plant_card_keys]

    assert len(MINE_COMPONENTS) == 4
    assert len(PLANT_COMPONENTS) == 5
    assert all(component.scope is ToolScope.MINE for component in MINE_COMPONENTS)
    assert CARGUIO_TRANSPORTE.scope is ToolScope.MINE
    assert all(component.scope is ToolScope.PLANT for component in PLANT_COMPONENTS)
    assert len(card_keys) == 22
    assert len(card_keys) == len(set(card_keys))
    assert 'carguio_global_turno' in card_keys
    assert 'mezcla_hacia_chancado' not in card_keys


def test_dashboard_builtin_bindings_use_supplied_tool_identity() -> None:
    components = {
        component.key: component.tool_component_key
        for component in (*MINE_COMPONENTS, *PLANT_COMPONENTS)
    }
    assert components == {
        'general_mina': 'cmp_general_mina_6df268db211b',
        'carguio': 'cmp_carguio_4cbd52aaa4b0',
        'transporte': 'cmp_transporte_67b979e9ab49',
        'chancado_stmg': 'cmp_chancado_stmg_abd7384135fd',
        'stockpile_chacay': 'cmp_stockpile_chacay_4265300400b1',
        'molienda': 'cmp_molienda_e3aaacbeb627',
        'flotacion': 'cmp_flotacion_9bbf64c07ea7',
        'transporte_fluidos': 'cmp_transporte_de_fluidos_823d86d77b46',
        'puerto': 'cmp_puerto_9f4e782f8c6a',
    }

    cards = {
        (component.key, card.key): card.tool_subcomponent_key
        for component in (*MINE_COMPONENTS, *PLANT_COMPONENTS)
        for card in component.cards
    }
    assert cards == {
        ('general_mina', 'movimiento_mina'): 'sub_movimiento_mina_1b6d8b556371',
        ('general_mina', 'remanentes'): 'sub_remanentes_6e22f5763660',
        ('general_mina', 'perforacion'): 'sub_perforacion_68a7f17fd16f',
        ('general_mina', 'mp10'): 'sub_mp10_7c12dfcc7294',
        ('carguio', 'carguio_global_turno'): 'sub_carguio_global_turno_90512312d37c',
        ('carguio', 'equipos_servicio'): 'sub_equipos_de_servicio_ebefaa434bb8',
        ('transporte', 'transporte_global'): 'sub_transporte_global_turno_ffda3898fa6f',
        ('transporte', 'numero_operativo'): 'sub_n_operativo_turno_12bb6dc5796e',
        ('transporte', 'tiempos_y_colas'): 'sub_tiempos_y_colas_108de76a6b6e',
        ('chancado_stmg', 'chancado_stmg'): 'sub_chancado_stmg_eaf0341c4200',
        ('stockpile_chacay', 'stockpile_chacay'): 'sub_stockpile_chacay_391a0d9c56cb',
        ('stockpile_chacay', 'tendencia_alimentado'): 'sub_tendencia_alimentado_98a0c47facaf',
        ('molienda', 'molienda'): 'sub_molienda_a8890f24edb7',
        ('flotacion', 'colectiva'): 'sub_colectiva_1144e0368316',
        ('flotacion', 'selectiva'): 'sub_selectiva_13ecce0283b4',
        ('transporte_fluidos', 'str'): 'sub_str_798d405ac5fe',
        ('transporte_fluidos', 'stc'): 'sub_stc_80570bfc1947',
        ('transporte_fluidos', 'tranque'): 'sub_tranque_72a1d5883f14',
        ('transporte_fluidos', 'sta'): 'sub_sta_f3f6b7525f63',
        ('puerto', 'puerto'): 'sub_puerto_1671f8c4ae3f',
        ('puerto', 'desaladora'): 'sub_desaladora_f41f09685011',
    }

    assert CARGUIO_TRANSPORTE.tool_component_key == 'cmp_carguio_4cbd52aaa4b0'
    assert CARGUIO_TRANSPORTE.tool_subcomponent_key == 'sub_gestion_carguio_turno_8a1701f8b1b3'
    assert CARGUIO_TRANSPORTE.linked_tool_component_keys == ('cmp_transporte_67b979e9ab49',)


def test_dashboard_layout_exposes_operational_scopes_and_card_display_inventory() -> None:
    nodes = tuple(_walk(build_dashboard_layout()))
    scopes = {
        _props(node).get('data-ada-operational-scope')
        for node in nodes
        if _props(node).get('data-ada-operational-scope') in {'mine', 'plant'}
    }
    targets = {
        _props(node).get('data-ada-io-presentation-target')
        for node in nodes
        if _props(node).get('data-ada-io-presentation-target')
    }
    cards = [node for node in nodes if _has_class(node, 'ada-card-display')]
    operational_wrappers = [
        node for node in nodes if _props(node).get('data-ada-content-state-operational') == 'true'
    ]

    assert scopes == {'mine', 'plant'}
    assert targets == {'overview', 'mine', 'plant'}
    assert len(cards) == 22
    assert len(operational_wrappers) == 22
    assert all(
        _props(node)['data-ada-content-state-runtime'] == 'true' for node in operational_wrappers
    )


def test_component_binding_projects_tool_identity_through_card_display() -> None:
    binding = DashboardComponentBinding(
        key='visual_component',
        label='Visual Component',
        scope=ToolScope.MINE,
        tool_component_key='tool_component',
        cards=(
            DashboardCardBinding(
                key='visual_card',
                label='Visual Card',
                tool_subcomponent_key='tool_subcomponent',
            ),
        ),
    )

    panel = build_component_panel(binding)
    nodes = tuple(_walk(panel))
    card = next(node for node in nodes if _has_class(node, 'ada-card-display'))
    wrapper = next(
        node for node in nodes if _props(node).get('data-ada-content-state-operational') == 'true'
    )

    assert _props(panel)['data-ada-component-key'] == 'tool_component'
    assert _props(card)['data-ada-component-key'] == 'tool_component'
    assert _props(card)['data-ada-subcomponent-key'] == 'tool_subcomponent'
    assert _props(card)['className'] == 'ada-card-display'
    assert 'data-ada-component-key' not in _props(wrapper)


def test_shared_card_projects_owner_and_linked_tool_identity_through_card_display() -> None:
    binding = DashboardSharedCardBinding(
        key='shared_visual_card',
        label='Shared Visual Card',
        scope=ToolScope.MINE,
        tool_component_key='owner_component',
        tool_subcomponent_key='shared_subcomponent',
        linked_tool_component_keys=('linked_component',),
    )

    wrapper = build_shared_dashboard_card(binding)
    card = next(node for node in _walk(wrapper) if _has_class(node, 'ada-card-display'))
    props = _props(card)

    assert _props(wrapper)['data-ada-content-state-operational'] == 'true'
    assert props['className'] == 'ada-card-display'
    assert props['data-ada-component-key'] == 'owner_component'
    assert props['data-ada-subcomponent-key'] == 'shared_subcomponent'
    assert props['data-ada-linked-component-keys'] == 'linked_component'
