import pytest

from ada.web.operational_render_binding import (
    OperationalComponentBinding,
    OperationalRenderBinding,
    OperationalRenderBindingError,
    bind_operational_render,
)
from ada.web.tools.enums import (
    ProcessLayoutRole,
    ToolConfigurationKind,
    ToolScope,
)
from ada.web.tools.structure import (
    ToolComponent,
    ToolStructure,
    ToolSubcomponent,
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
                subcomponents=(ToolSubcomponent(key='palas', display_name='Palas'),),
            ),
            ToolComponent(
                key='transporte',
                display_name='Transporte',
                scope=ToolScope.MINE,
                subcomponents=(ToolSubcomponent(key='camiones', display_name='Camiones'),),
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


def test_binding_is_derived_exclusively_from_tool_structure() -> None:
    structure = _integrated_structure()

    binding = bind_operational_render(structure)

    assert binding.structure is structure
    assert binding.component_keys == ('carguio', 'transporte')
    assert tuple(item.component for item in binding.components) == structure.components


def test_binding_rejects_non_tool_structure() -> None:
    with pytest.raises(
        OperationalRenderBindingError,
        match='Operational render requires ToolStructure',
    ):
        bind_operational_render(object())


def test_render_binding_requires_exact_structure_order() -> None:
    structure = _integrated_structure()

    with pytest.raises(
        OperationalRenderBindingError,
        match='Operational render component order must follow Tool Structure',
    ):
        OperationalRenderBinding(
            structure=structure,
            components=(
                OperationalComponentBinding(component=structure.components[1]),
                OperationalComponentBinding(component=structure.components[0]),
            ),
        )


def test_render_binding_requires_one_binding_per_component() -> None:
    structure = _integrated_structure()

    with pytest.raises(
        OperationalRenderBindingError,
        match='must contain one binding per Tool component',
    ):
        OperationalRenderBinding(
            structure=structure,
            components=(OperationalComponentBinding(component=structure.components[0]),),
        )


def test_process_center_remains_one_component_binding_with_many_subcomponents() -> None:
    binding = bind_operational_render(_process_structure())

    assert len(binding.components) == 1
    assert tuple(item.key for item in binding.components[0].component.subcomponents) == (
        'rougher',
        'cleaner',
        'scavenger',
    )


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
                subcomponents=(ToolSubcomponent(key='camiones', display_name='Camiones'),),
            ),
        ),
    )

    binding = bind_operational_render(structure)

    assert binding.component_keys == ('carguio', 'transporte')
    assert len(binding.components) == 2
    assert binding.components[0].component.subcomponents[0].linked_component_keys == ('transporte',)


def test_strategic_uses_same_binding_contract_without_kind_specific_render_logic() -> None:
    structure = ToolStructure(
        tool_key='strategic_tool',
        kind=ToolConfigurationKind.STRATEGIC,
        components=(ToolComponent(key='overview', display_name='Overview'),),
    )

    binding = bind_operational_render(structure)

    assert binding.structure.kind is ToolConfigurationKind.STRATEGIC
    assert binding.component_keys == ('overview',)
