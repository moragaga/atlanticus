import pytest

from ada.configuration.tools import (
    ToolConfiguration,
    ToolConfigurationKind,
)
from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.web.configuration.tool_editor import (
    ToolStructureEditorValidationError,
    build_structure_from_editor_tables,
    structure_editor_coverage_from_configuration,
)


def _base(kind: ToolConfigurationKind) -> ToolConfiguration:
    key = (
        'process'
        if kind is ToolConfigurationKind.PROCESS
        else 'integrated_operations'
    )
    return ToolConfiguration(
        tool_key=key,
        display_name='Tool',
        kind=kind,
        source_consumption=ToolSourceConsumption(
            tool_key=key,
            source_keys=('pi',),
        ),
        source_operational_participation=(
            ToolSourceOperationalParticipation(
                tool_key=key,
                control_sources=(
                    SourceControlPolicy('pi', 200, 300),
                ),
            )
        ),
    )


def test_process_coverage_maps_to_structure_operational_scope() -> None:
    base = _base(ToolConfigurationKind.PROCESS)
    structure = build_structure_from_editor_tables(
        base_configuration=base,
        coverage='plant',
        component_rows=[
            {
                'key': 'center',
                'display_name': 'Centro',
                'scope': None,
                'layout_role': 'center',
            }
        ],
        subcomponent_rows=[
            {
                'owner_component_key': 'center',
                'key': 'primary',
                'display_name': 'Principal',
                'linked_component_keys': [],
            }
        ],
    )

    configured = ToolConfiguration(
        tool_key=base.tool_key,
        display_name=base.display_name,
        kind=base.kind,
        source_consumption=base.source_consumption,
        source_operational_participation=base.source_operational_participation,
        structure=structure,
    )

    assert structure.operational_scope is not None
    assert structure.operational_scope.value == 'plant'
    assert structure_editor_coverage_from_configuration(configured) == 'plant'


def test_integrated_single_scope_is_inherited_by_components() -> None:
    structure = build_structure_from_editor_tables(
        base_configuration=_base(ToolConfigurationKind.INTEGRATED_OPERATIONS),
        coverage='mine',
        component_rows=[
            {
                'key': 'mine',
                'display_name': 'Mina',
                'scope': None,
                'layout_role': None,
            }
        ],
        subcomponent_rows=[
            {
                'owner_component_key': 'mine',
                'key': 'extraction',
                'display_name': 'Extracción',
                'linked_component_keys': [],
            }
        ],
    )

    assert structure.component('mine').scope is not None
    assert structure.component('mine').scope.value == 'mine'


def test_integrated_mine_and_plant_requires_both_scopes() -> None:
    with pytest.raises(
        ToolStructureEditorValidationError,
        match='at least one component',
    ):
        build_structure_from_editor_tables(
            base_configuration=_base(
                ToolConfigurationKind.INTEGRATED_OPERATIONS
            ),
            coverage='mine_plant',
            component_rows=[
                {
                    'key': 'mine',
                    'display_name': 'Mina',
                    'scope': 'mine',
                    'layout_role': None,
                }
            ],
            subcomponent_rows=[
                {
                    'owner_component_key': 'mine',
                    'key': 'extraction',
                    'display_name': 'Extracción',
                    'linked_component_keys': [],
                }
            ],
        )


def test_integrated_shared_subcomponent_keeps_one_owner() -> None:
    structure = build_structure_from_editor_tables(
        base_configuration=_base(ToolConfigurationKind.INTEGRATED_OPERATIONS),
        coverage='mine',
        component_rows=[
            {
                'key': 'mine',
                'display_name': 'Mina',
                'scope': None,
                'layout_role': None,
            },
            {
                'key': 'dispatch',
                'display_name': 'Despacho',
                'scope': None,
                'layout_role': None,
            },
        ],
        subcomponent_rows=[
            {
                'owner_component_key': 'mine',
                'key': 'extraction',
                'display_name': 'Extracción',
                'linked_component_keys': ['dispatch'],
            },
            {
                'owner_component_key': 'dispatch',
                'key': 'fleet',
                'display_name': 'Flota',
                'linked_component_keys': [],
            },
        ],
    )

    extraction = structure.component('mine').subcomponent('extraction')
    assert extraction.linked_component_keys == ('dispatch',)
    assert (
        structure.subcomponent_address(
            component_key='dispatch',
            subcomponent_key='extraction',
        ).owner_component_key
        == 'mine'
    )
