from __future__ import annotations

from dash import html

from ada.configuration.tools import (
    ToolComponent,
    ToolConfigurationKind,
    ToolScope,
    ToolStructure,
    ToolSubcomponent,
    ToolSubcomponentAddress,
)
from ada.web.application.generic.operational_render import materialize_operational_components
from ada.web.component_store import ComponentStoreSnapshot, ComponentStoreState
from ada.web.operational_render_binding import bind_operational_render


def _structure() -> ToolStructure:
    return ToolStructure(
        tool_key='operational_tool',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='mine',
                display_name='Mina',
                scope=ToolScope.MINE,
                subcomponents=(
                    ToolSubcomponent(
                        key='mine_phase',
                        display_name='Fase Mina',
                        linked_component_keys=('haulage',),
                    ),
                ),
            ),
            ToolComponent(
                key='haulage',
                display_name='Transporte',
                scope=ToolScope.MINE,
                subcomponents=(
                    ToolSubcomponent(key='haulage_phase', display_name='Fase Transporte'),
                ),
            ),
            ToolComponent(
                key='plant',
                display_name='Planta',
                scope=ToolScope.PLANT,
                subcomponents=(ToolSubcomponent(key='plant_phase', display_name='Fase Planta'),),
            ),
        ),
    )


def _binding(*, populated_mine: bool = False):
    structure = _structure()
    mine_payload = {'value': 42} if populated_mine else None
    stores = (
        ComponentStoreSnapshot(
            tool_key=structure.tool_key,
            component_key='mine',
            payload=mine_payload,
        ),
        ComponentStoreSnapshot(
            tool_key=structure.tool_key,
            component_key='haulage',
        ),
        ComponentStoreSnapshot(
            tool_key=structure.tool_key,
            component_key='plant',
        ),
    )
    return bind_operational_render(structure, stores), mine_payload


def test_materialization_uses_structure_order_and_preserves_original_bindings() -> None:
    binding, _payload = _binding()
    observed = []

    def render_component(render_binding, component_binding):
        assert render_binding is binding
        observed.append(component_binding)
        return html.Div(
            component_binding.component.display_name,
            id=f'rendered-{component_binding.component.key}',
        )

    rendered = materialize_operational_components(
        binding,
        renderers={
            'plant': render_component,
            'haulage': render_component,
            'mine': render_component,
        },
    )

    assert tuple(component.id for component in rendered) == (
        'rendered-mine',
        'rendered-haulage',
        'rendered-plant',
    )
    assert tuple(observed) == binding.components
    assert tuple(item.store.state for item in observed) == (
        ComponentStoreState.EMPTY,
        ComponentStoreState.EMPTY,
        ComponentStoreState.EMPTY,
    )


def test_renderer_can_resolve_linked_subcomponent_to_single_owner_store() -> None:
    binding, payload = _binding(populated_mine=True)
    observed_owner_stores = []

    def render_component(render_binding, component_binding):
        if component_binding.component.key == 'haulage':
            address = render_binding.structure.subcomponent_address(
                component_key='haulage',
                subcomponent_key='mine_phase',
            )
            assert address == ToolSubcomponentAddress('mine', 'mine_phase')
            owner_binding = next(
                item
                for item in render_binding.components
                if item.component.key == address.owner_component_key
            )
            observed_owner_stores.append(owner_binding.store)
        return html.Div(id=f'rendered-{component_binding.component.key}')

    materialize_operational_components(
        binding,
        renderers={
            'mine': render_component,
            'haulage': render_component,
            'plant': render_component,
        },
    )

    assert len(observed_owner_stores) == 1
    assert observed_owner_stores[0] is binding.components[0].store
    assert observed_owner_stores[0].payload is payload
    assert binding.components[1].store.payload is None


def test_materialization_preserves_populated_payload_without_normalization() -> None:
    binding, payload = _binding(populated_mine=True)
    observed_payloads = []

    def render_component(_render_binding, component_binding):
        observed_payloads.append(component_binding.store.payload)
        return html.Div(id=f'rendered-{component_binding.component.key}')

    materialize_operational_components(
        binding,
        renderers={
            'mine': render_component,
            'haulage': render_component,
            'plant': render_component,
        },
    )

    assert binding.components[0].store.state is ComponentStoreState.POPULATED
    assert observed_payloads[0] is payload
    assert observed_payloads[1:] == [None, None]


def test_materialization_requires_renderer_for_every_configured_component() -> None:
    binding, _payload = _binding()

    try:
        materialize_operational_components(
            binding,
            renderers={
                'mine': lambda _render_binding, _binding: html.Div(),
                'haulage': lambda _render_binding, _binding: html.Div(),
            },
        )
    except ValueError as error:
        assert str(error) == "Missing operational component renderer: 'plant'"
    else:
        raise AssertionError('Expected missing operational component renderer to fail')


def test_materialization_rejects_renderer_for_unknown_component() -> None:
    binding, _payload = _binding()

    try:
        materialize_operational_components(
            binding,
            renderers={
                'mine': lambda _render_binding, _binding: html.Div(),
                'haulage': lambda _render_binding, _binding: html.Div(),
                'plant': lambda _render_binding, _binding: html.Div(),
                'port': lambda _render_binding, _binding: html.Div(),
            },
        )
    except ValueError as error:
        assert str(error) == "Unknown operational component renderer: 'port'"
    else:
        raise AssertionError('Expected unknown operational component renderer to fail')


def test_materialization_rejects_non_callable_renderer() -> None:
    binding, _payload = _binding()

    try:
        materialize_operational_components(
            binding,
            renderers={
                'mine': object(),
                'haulage': lambda _render_binding, _binding: html.Div(),
                'plant': lambda _render_binding, _binding: html.Div(),
            },
        )
    except TypeError as error:
        assert str(error) == "Operational component renderer must be callable: 'mine'"
    else:
        raise AssertionError('Expected non-callable operational component renderer to fail')


def test_materialization_requires_dash_component_result() -> None:
    binding, _payload = _binding()

    try:
        materialize_operational_components(
            binding,
            renderers={
                'mine': lambda _render_binding, _binding: object(),
                'haulage': lambda _render_binding, _binding: html.Div(),
                'plant': lambda _render_binding, _binding: html.Div(),
            },
        )
    except TypeError as error:
        assert str(error) == ("Operational component renderer must return a Dash Component: 'mine'")
    else:
        raise AssertionError('Expected invalid operational component renderer result to fail')
