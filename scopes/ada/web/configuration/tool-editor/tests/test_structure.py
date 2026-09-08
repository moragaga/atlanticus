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
                'key': 'cmp_process',
                'display_name': 'Proceso',
                'scope': None,
            }
        ],
        subcomponent_rows=[
            {
                'owner_component_key': 'cmp_process',
                'key': 'sub_primary',
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
    assert structure.components[0].layout_role is None
    assert structure_editor_coverage_from_configuration(configured) == 'plant'


def test_integrated_operations_rejects_single_scope_coverage() -> None:
    with pytest.raises(
        ToolStructureEditorValidationError,
        match='must be Mina y Planta',
    ):
        build_structure_from_editor_tables(
            base_configuration=_base(
                ToolConfigurationKind.INTEGRATED_OPERATIONS
            ),
            coverage='mine',
            component_rows=[],
            subcomponent_rows=[],
        )


def test_integrated_mine_and_plant_requires_both_scopes() -> None:
    with pytest.raises(
        ToolStructureEditorValidationError,
        match='requires both Mina and Planta',
    ):
        build_structure_from_editor_tables(
            base_configuration=_base(
                ToolConfigurationKind.INTEGRATED_OPERATIONS
            ),
            coverage='mine_plant',
            component_rows=[
                {
                    'key': 'cmp_mine',
                    'display_name': 'Mina',
                    'scope': 'mine',
                }
            ],
            subcomponent_rows=[
                {
                    'owner_component_key': 'cmp_mine',
                    'key': 'sub_extraction',
                    'display_name': 'Extracción',
                    'linked_component_keys': [],
                }
            ],
        )


def test_integrated_shared_subcomponent_keeps_one_owner() -> None:
    structure = build_structure_from_editor_tables(
        base_configuration=_base(
            ToolConfigurationKind.INTEGRATED_OPERATIONS
        ),
        coverage='mine_plant',
        component_rows=[
            {
                'key': 'cmp_mine',
                'display_name': 'Mina',
                'scope': 'mine',
            },
            {
                'key': 'cmp_dispatch',
                'display_name': 'Despacho',
                'scope': 'mine',
            },
            {
                'key': 'cmp_plant',
                'display_name': 'Planta',
                'scope': 'plant',
            },
        ],
        subcomponent_rows=[
            {
                'owner_component_key': 'cmp_mine',
                'key': 'sub_extraction',
                'display_name': 'Extracción',
                'linked_component_keys': ['cmp_dispatch'],
            },
            {
                'owner_component_key': 'cmp_dispatch',
                'key': 'sub_fleet',
                'display_name': 'Flota',
                'linked_component_keys': [],
            },
            {
                'owner_component_key': 'cmp_plant',
                'key': 'sub_crusher',
                'display_name': 'Chancado',
                'linked_component_keys': [],
            },
        ],
    )

    extraction = structure.component('cmp_mine').subcomponent(
        'sub_extraction'
    )
    assert extraction.linked_component_keys == ('cmp_dispatch',)
    assert (
        structure.subcomponent_address(
            component_key='cmp_dispatch',
            subcomponent_key='sub_extraction',
        ).owner_component_key
        == 'cmp_mine'
    )
