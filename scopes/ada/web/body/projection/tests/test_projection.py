import pytest

from ada.configuration.tools import (
    ProcessLayoutRole,
    ToolComponent,
    ToolConfigurationKind,
    ToolScope,
    ToolStructure,
    ToolSubcomponent,
)
from ada.web.body.projection import ToolBodyProjectionError, project_tool_body


def _process_structure() -> ToolStructure:
    return ToolStructure(
        tool_key='mine_process',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.MINE,
        components=(
            ToolComponent(
                key='left_context',
                display_name='Left Context',
                layout_role=ProcessLayoutRole.LEFT,
            ),
            ToolComponent(
                key='mine',
                display_name='Mina',
                layout_role=ProcessLayoutRole.CENTER,
                subcomponents=(
                    ToolSubcomponent(key='loading', display_name='Carguío'),
                    ToolSubcomponent(key='transport', display_name='Transporte'),
                    ToolSubcomponent(key='crushing', display_name='Chancado'),
                ),
            ),
            ToolComponent(
                key='right_context',
                display_name='Right Context',
                layout_role=ProcessLayoutRole.RIGHT,
            ),
            ToolComponent(
                key='bottom_context',
                display_name='Bottom Context',
                layout_role=ProcessLayoutRole.BOTTOM,
            ),
        ),
    )


def _integrated_operations_structure() -> ToolStructure:
    return ToolStructure(
        tool_key='integrated_operations',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='loading',
                display_name='Carguío',
                scope=ToolScope.MINE,
                subcomponents=(
                    ToolSubcomponent(
                        key='shift_management',
                        display_name='Gestión Turno',
                        linked_component_keys=('transport',),
                    ),
                ),
            ),
            ToolComponent(
                key='transport',
                display_name='Transporte',
                scope=ToolScope.MINE,
                subcomponents=(ToolSubcomponent(key='fleet', display_name='Flota'),),
            ),
            ToolComponent(
                key='grinding',
                display_name='Molienda',
                scope=ToolScope.PLANT,
                subcomponents=(ToolSubcomponent(key='sag', display_name='SAG'),),
            ),
        ),
    )


def test_process_projection_preserves_layout_roles_and_resolves_scope() -> None:
    projection = project_tool_body(_process_structure())

    assert projection.root_id == 'ada-tool-mine_process-body'
    assert projection.component_keys == (
        'left_context',
        'mine',
        'right_context',
        'bottom_context',
    )
    center = projection.component_for_layout_role(ProcessLayoutRole.CENTER)
    assert center.component_key == 'mine'
    assert center.scope is ToolScope.MINE
    assert center.wrapper_id == 'ada-tool-mine_process-component-mine'
    assert tuple(item.subcomponent_key for item in center.subcomponents) == (
        'loading',
        'transport',
        'crushing',
    )


def test_process_single_center_subcomponent_keeps_same_contract() -> None:
    structure = ToolStructure(
        tool_key='flotation_process',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.PLANT,
        components=(
            ToolComponent(
                key='flotation',
                display_name='Flotación',
                layout_role=ProcessLayoutRole.CENTER,
                subcomponents=(ToolSubcomponent(key='flotation', display_name='Flotación'),),
            ),
        ),
    )

    projection = project_tool_body(structure)
    center = projection.component_for_layout_role(ProcessLayoutRole.CENTER)

    assert center.component_key == 'flotation'
    assert center.scope is ToolScope.PLANT
    assert center.subcomponents[0].wrapper_id == (
        'ada-tool-flotation_process-subcomponent-flotation-flotation'
    )


def test_integrated_operations_projection_supports_n_components() -> None:
    projection = project_tool_body(_integrated_operations_structure())

    assert projection.component_keys == ('loading', 'transport', 'grinding')
    assert projection.component('loading').scope is ToolScope.MINE
    assert projection.component('transport').scope is ToolScope.MINE
    assert projection.component('grinding').scope is ToolScope.PLANT
    assert all(item.layout_role is None for item in projection.components)


def test_shared_subcomponent_keeps_single_canonical_wrapper() -> None:
    projection = project_tool_body(_integrated_operations_structure())

    direct = projection.subcomponent(
        component_key='loading',
        subcomponent_key='shift_management',
    )
    linked = projection.subcomponent(
        component_key='transport',
        subcomponent_key='shift_management',
    )

    assert direct is linked
    assert direct.owner_component_key == 'loading'
    assert direct.visible_component_keys == ('loading', 'transport')
    assert direct.wrapper_id == (
        'ada-tool-integrated_operations-subcomponent-loading-shift_management'
    )


def test_unknown_subcomponent_is_rejected() -> None:
    projection = project_tool_body(_integrated_operations_structure())

    with pytest.raises(ToolBodyProjectionError, match='Unknown Tool body subcomponent'):
        projection.subcomponent(
            component_key='transport',
            subcomponent_key='missing',
        )


def test_projection_document_contains_identity_bindings_only() -> None:
    document = project_tool_body(_integrated_operations_structure()).to_document()

    assert document['tool_key'] == 'integrated_operations'
    assert document['kind'] == 'integrated_operations'
    assert document['root_id'] == 'ada-tool-integrated_operations-body'
    loading = document['components'][0]
    assert loading['component_key'] == 'loading'
    assert loading['scope'] == 'mine'
    assert loading['layout_role'] is None
    assert loading['wrapper_id'] == 'ada-tool-integrated_operations-component-loading'
    assert loading['subcomponents'][0]['linked_component_keys'] == ['transport']
