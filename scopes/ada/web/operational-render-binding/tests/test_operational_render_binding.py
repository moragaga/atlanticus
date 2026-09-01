import pytest

from ada.configuration.tools import (
    ProcessLayoutRole,
    ToolComponent,
    ToolConfigurationKind,
    ToolScope,
    ToolStructure,
    ToolSubcomponent,
)
from ada.web.component_store import ComponentStoreSnapshot, ComponentStoreState
from ada.web.operational_render_binding import (
    OperationalRenderBindingError,
    bind_operational_render,
)


def _integrated_structure() -> ToolStructure:
    return ToolStructure(
        tool_key='integrated_ops',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='carguio',
                display_name='Carguío',
                scope=ToolScope.MINE,
                subcomponents=(
                    ToolSubcomponent(key='palas', display_name='Palas'),
                ),
            ),
            ToolComponent(
                key='transporte',
                display_name='Transporte',
                scope=ToolScope.MINE,
                subcomponents=(
                    ToolSubcomponent(key='camiones', display_name='Camiones'),
                ),
            ),
        ),
    )


def _process_structure() -> ToolStructure:
    return ToolStructure(
        tool_key='process_tool',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.PLANT,
        components=(
            ToolComponent(
                key='flotacion',
                display_name='Flotación',
                layout_role=ProcessLayoutRole.CENTER,
                subcomponents=(
                    ToolSubcomponent(key='rougher', display_name='Rougher'),
                    ToolSubcomponent(key='cleaner', display_name='Cleaner'),
                    ToolSubcomponent(key='scavenger', display_name='Scavenger'),
                ),
            ),
        ),
    )


def test_binding_mounts_all_structural_components_with_empty_stores() -> None:
    structure = _integrated_structure()
    binding = bind_operational_render(
        structure,
        (
            ComponentStoreSnapshot(tool_key='integrated_ops', component_key='carguio'),
            ComponentStoreSnapshot(tool_key='integrated_ops', component_key='transporte'),
        ),
    )

    assert binding.structure is structure
    assert binding.component_keys == ('carguio', 'transporte')
    assert all(item.store.state is ComponentStoreState.EMPTY for item in binding.components)


def test_binding_order_is_always_driven_by_tool_structure() -> None:
    structure = _integrated_structure()
    binding = bind_operational_render(
        structure,
        (
            ComponentStoreSnapshot(tool_key='integrated_ops', component_key='transporte'),
            ComponentStoreSnapshot(tool_key='integrated_ops', component_key='carguio'),
        ),
    )

    assert binding.component_keys == ('carguio', 'transporte')


def test_binding_preserves_hydrated_payload_without_interpreting_it() -> None:
    structure = _integrated_structure()
    payload = {'latest': {'tonnes': 42}, 'series': (1, 2, 3)}
    binding = bind_operational_render(
        structure,
        (
            ComponentStoreSnapshot(
                tool_key='integrated_ops',
                component_key='carguio',
                payload=payload,
            ),
            ComponentStoreSnapshot(tool_key='integrated_ops', component_key='transporte'),
        ),
    )

    assert binding.components[0].store.payload is payload
    assert binding.components[0].store.state is ComponentStoreState.POPULATED
    assert binding.components[1].store.state is ComponentStoreState.EMPTY


def test_binding_rejects_missing_store_for_structural_component() -> None:
    with pytest.raises(
        OperationalRenderBindingError,
        match="Missing Operational Render Component Store: 'transporte'",
    ):
        bind_operational_render(
            _integrated_structure(),
            (ComponentStoreSnapshot(tool_key='integrated_ops', component_key='carguio'),),
        )


def test_binding_rejects_store_not_declared_by_tool_structure() -> None:
    with pytest.raises(
        OperationalRenderBindingError,
        match="Unknown Operational Render Component Store: 'chancado'",
    ):
        bind_operational_render(
            _integrated_structure(),
            (
                ComponentStoreSnapshot(tool_key='integrated_ops', component_key='carguio'),
                ComponentStoreSnapshot(tool_key='integrated_ops', component_key='transporte'),
                ComponentStoreSnapshot(tool_key='integrated_ops', component_key='chancado'),
            ),
        )


def test_binding_rejects_store_from_another_tool() -> None:
    with pytest.raises(
        OperationalRenderBindingError,
        match='Operational render Component Store tool key must match Tool Structure',
    ):
        bind_operational_render(
            _integrated_structure(),
            (
                ComponentStoreSnapshot(tool_key='another_tool', component_key='carguio'),
                ComponentStoreSnapshot(tool_key='integrated_ops', component_key='transporte'),
            ),
        )


def test_binding_rejects_duplicate_store_for_component() -> None:
    with pytest.raises(
        OperationalRenderBindingError,
        match="Duplicate Operational Render Component Store: 'carguio'",
    ):
        bind_operational_render(
            _integrated_structure(),
            (
                ComponentStoreSnapshot(tool_key='integrated_ops', component_key='carguio'),
                ComponentStoreSnapshot(tool_key='integrated_ops', component_key='carguio'),
                ComponentStoreSnapshot(tool_key='integrated_ops', component_key='transporte'),
            ),
        )


def test_process_center_remains_one_component_binding_with_many_subcomponents() -> None:
    structure = _process_structure()
    binding = bind_operational_render(
        structure,
        (ComponentStoreSnapshot(tool_key='process_tool', component_key='flotacion'),),
    )

    assert len(binding.components) == 1
    assert tuple(
        item.key for item in binding.components[0].component.subcomponents
    ) == ('rougher', 'cleaner', 'scavenger')


def test_linked_subcomponent_does_not_create_an_extra_component_binding() -> None:
    structure = ToolStructure(
        tool_key='shared_ops',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='carguio',
                display_name='Carguío',
                scope=ToolScope.MINE,
                subcomponents=(
                    ToolSubcomponent(
                        key='shared_front',
                        display_name='Frente compartido',
                        linked_component_keys=('transporte',),
                    ),
                ),
            ),
            ToolComponent(
                key='transporte',
                display_name='Transporte',
                scope=ToolScope.MINE,
                subcomponents=(
                    ToolSubcomponent(key='camiones', display_name='Camiones'),
                ),
            ),
        ),
    )
    binding = bind_operational_render(
        structure,
        (
            ComponentStoreSnapshot(tool_key='shared_ops', component_key='carguio'),
            ComponentStoreSnapshot(tool_key='shared_ops', component_key='transporte'),
        ),
    )

    assert binding.component_keys == ('carguio', 'transporte')
    assert len(binding.components) == 2
    assert binding.components[0].component.subcomponents[0].linked_component_keys == (
        'transporte',
    )


def test_strategic_uses_same_binding_contract_without_kind_specific_render_logic() -> None:
    structure = ToolStructure(
        tool_key='strategic_tool',
        kind=ToolConfigurationKind.STRATEGIC,
        components=(
            ToolComponent(key='overview', display_name='Overview'),
        ),
    )
    binding = bind_operational_render(
        structure,
        (ComponentStoreSnapshot(tool_key='strategic_tool', component_key='overview'),),
    )

    assert binding.structure.kind is ToolConfigurationKind.STRATEGIC
    assert binding.component_keys == ('overview',)
