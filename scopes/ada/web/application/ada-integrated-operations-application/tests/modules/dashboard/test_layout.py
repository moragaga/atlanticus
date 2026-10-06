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


def test_dashboard_layout_exposes_operational_scopes_and_presentation_targets() -> None:
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
    cards = [node for node in nodes if _props(node).get('data-ada-io-card-key')]

    assert scopes == {'mine', 'plant'}
    assert targets == {'overview', 'mine', 'plant'}
    assert len(cards) == 22


def test_component_binding_projects_tool_identity_without_layout_changes() -> None:
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
    card = next(node for node in nodes if _props(node).get('data-ada-io-card-key'))

    assert _props(panel)['data-ada-component-key'] == 'tool_component'
    assert _props(card)['data-ada-component-key'] == 'tool_component'
    assert _props(card)['data-ada-subcomponent-key'] == 'tool_subcomponent'


def test_shared_card_projects_owner_and_linked_tool_identity() -> None:
    binding = DashboardSharedCardBinding(
        key='shared_visual_card',
        label='Shared Visual Card',
        scope=ToolScope.MINE,
        tool_component_key='owner_component',
        tool_subcomponent_key='shared_subcomponent',
        linked_tool_component_keys=('linked_component',),
    )

    card = build_shared_dashboard_card(binding)
    props = _props(card)

    assert props['data-ada-component-key'] == 'owner_component'
    assert props['data-ada-subcomponent-key'] == 'shared_subcomponent'
    assert props['data-ada-linked-component-keys'] == 'linked_component'
