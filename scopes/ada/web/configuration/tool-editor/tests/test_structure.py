from __future__ import annotations

import pytest

from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.configuration.tools import ToolConfiguration, ToolConfigurationKind
from ada.web.configuration.tool_editor import (
    ToolStructureEditorValidationError,
    build_configuration_from_structure_editor,
    build_structure_from_editor_tables,
    structure_editor_table_data_from_configuration,
)


def base_configuration(kind: ToolConfigurationKind) -> ToolConfiguration:
    return ToolConfiguration(
        tool_key='operations',
        display_name='Operaciones',
        kind=kind,
        source_consumption=ToolSourceConsumption(
            tool_key='operations',
            source_keys=('pi',),
        ),
        source_operational_participation=ToolSourceOperationalParticipation(
            tool_key='operations',
            control_sources=(
                SourceControlPolicy(
                    source_key='pi',
                    pre_degrading_after_seconds=200,
                    degrading_after_seconds=300,
                ),
            ),
            additional_observation_source_keys=(),
        ),
        structure=None,
    )


def test_process_structure_is_built_by_domain_contract() -> None:
    base = base_configuration(ToolConfigurationKind.PROCESS)

    structure = build_structure_from_editor_tables(
        base_configuration=base,
        operational_scope='plant',
        component_rows=[
            {
                'key': 'crusher',
                'display_name': 'Chancado',
                'scope': None,
                'layout_role': 'center',
            }
        ],
        subcomponent_rows=[
            {
                'owner_component_key': 'crusher',
                'key': 'primary',
                'display_name': 'Primario',
                'linked_component_keys': '',
            }
        ],
    )

    assert structure.operational_scope is not None
    assert structure.operational_scope.value == 'plant'
    assert structure.component('crusher').subcomponent('primary').display_name == 'Primario'
    assert structure.kpi_destination_keys == (
        'global_indicators',
        'time_status',
        'crusher',
    )


def test_integrated_operations_structure_supports_linked_subcomponents() -> None:
    base = base_configuration(ToolConfigurationKind.INTEGRATED_OPERATIONS)

    structure = build_structure_from_editor_tables(
        base_configuration=base,
        operational_scope=None,
        component_rows=[
            {
                'key': 'mine',
                'display_name': 'Mina',
                'scope': 'mine',
                'layout_role': None,
            },
            {
                'key': 'dispatch',
                'display_name': 'Despacho',
                'scope': 'mine',
                'layout_role': None,
            },
        ],
        subcomponent_rows=[
            {
                'owner_component_key': 'mine',
                'key': 'extraction',
                'display_name': 'Extracción',
                'linked_component_keys': 'dispatch',
            },
            {
                'owner_component_key': 'dispatch',
                'key': 'fleet',
                'display_name': 'Flota',
                'linked_component_keys': '',
            },
        ],
    )

    extraction = structure.component('mine').subcomponent('extraction')
    assert extraction.linked_component_keys == ('dispatch',)
    assert structure.kpi_destination_keys == (
        'global_indicators',
        'time_status',
        'mine',
        'dispatch',
    )


def test_unknown_subcomponent_owner_is_rejected_before_domain_nesting() -> None:
    base = base_configuration(ToolConfigurationKind.PROCESS)

    with pytest.raises(
        ToolStructureEditorValidationError,
        match='owner component does not exist',
    ):
        build_structure_from_editor_tables(
            base_configuration=base,
            operational_scope='plant',
            component_rows=[
                {
                    'key': 'crusher',
                    'display_name': 'Chancado',
                    'scope': None,
                    'layout_role': 'center',
                }
            ],
            subcomponent_rows=[
                {
                    'owner_component_key': 'unknown',
                    'key': 'primary',
                    'display_name': 'Primario',
                    'linked_component_keys': '',
                }
            ],
        )


def test_structure_merge_preserves_tool_identity_and_sources() -> None:
    base = base_configuration(ToolConfigurationKind.PROCESS)
    structure = build_structure_from_editor_tables(
        base_configuration=base,
        operational_scope='plant',
        component_rows=[
            {
                'key': 'crusher',
                'display_name': 'Chancado',
                'scope': None,
                'layout_role': 'center',
            }
        ],
        subcomponent_rows=[
            {
                'owner_component_key': 'crusher',
                'key': 'primary',
                'display_name': 'Primario',
                'linked_component_keys': '',
            }
        ],
    )

    merged = build_configuration_from_structure_editor(
        base_configuration=base,
        structure_document=structure.to_document(),
    )

    assert merged.tool_key == base.tool_key
    assert merged.display_name == base.display_name
    assert merged.source_consumption == base.source_consumption
    assert merged.source_operational_participation == base.source_operational_participation
    assert merged.structure == structure


def test_existing_structure_round_trips_to_editor_tables() -> None:
    base = base_configuration(ToolConfigurationKind.PROCESS)
    structure = build_structure_from_editor_tables(
        base_configuration=base,
        operational_scope='plant',
        component_rows=[
            {
                'key': 'crusher',
                'display_name': 'Chancado',
                'scope': None,
                'layout_role': 'center',
            }
        ],
        subcomponent_rows=[
            {
                'owner_component_key': 'crusher',
                'key': 'primary',
                'display_name': 'Primario',
                'linked_component_keys': '',
            }
        ],
    )
    configured = build_configuration_from_structure_editor(
        base_configuration=base,
        structure_document=structure.to_document(),
    )

    components, subcomponents, operational_scope = structure_editor_table_data_from_configuration(
        configured
    )

    assert operational_scope == 'plant'
    assert components == [
        {
            'key': 'crusher',
            'display_name': 'Chancado',
            'scope': None,
            'layout_role': 'center',
        }
    ]
    assert subcomponents == [
        {
            'owner_component_key': 'crusher',
            'key': 'primary',
            'display_name': 'Primario',
            'linked_component_keys': '',
        }
    ]
