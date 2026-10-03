import pytest

from ada.contracts.tools import (
    ProcessLayoutRole,
    SourceControlPolicy,
    ToolComponent,
    ToolConfigurationKind,
    ToolDependencyEntry,
    ToolDependencyManifest,
    ToolScope,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
    ToolStructure,
    ToolSubcomponent,
    validate_operational_participation_against_consumption,
)
from ada.contracts.tools.errors import ToolConfigurationValidationError
from ada.contracts.tools.sources.errors import (
    ToolSourceOperationalParticipationValidationError,
)


def test_tool_structure_roundtrip_preserves_document_contract():
    structure = ToolStructure(
        tool_key='crusher',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.PLANT,
        components=(
            ToolComponent(
                key='main',
                display_name='Main',
                layout_role=ProcessLayoutRole.CENTER,
                subcomponents=(ToolSubcomponent(key='motor', display_name='Motor'),),
            ),
        ),
    )

    document = structure.to_document()

    assert ToolStructure.from_document(document).to_document() == document
    assert document == {
        'tool_key': 'crusher',
        'kind': 'process',
        'operational_scope': 'plant',
        'components': [
            {
                'key': 'main',
                'display_name': 'Main',
                'subcomponents': [
                    {
                        'key': 'motor',
                        'display_name': 'Motor',
                        'linked_component_keys': [],
                    }
                ],
                'layout_role': 'center',
            }
        ],
    }


def test_integrated_operations_visible_linked_subcomponent_is_preserved():
    structure = ToolStructure(
        tool_key='integrated',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='mine',
                display_name='Mine',
                scope=ToolScope.MINE,
                subcomponents=(
                    ToolSubcomponent(
                        key='shared',
                        display_name='Shared',
                        linked_component_keys=('plant',),
                    ),
                ),
            ),
            ToolComponent(
                key='plant',
                display_name='Plant',
                scope=ToolScope.MINE,
                subcomponents=(ToolSubcomponent(key='local', display_name='Local'),),
            ),
        ),
    )

    assert structure.subcomponent_address(
        component_key='plant', subcomponent_key='shared'
    ).owner_component_key == 'mine'


def test_manifest_roundtrip_and_order_are_stable():
    def entry(key):
        structure = ToolStructure(
            tool_key=key,
            kind=ToolConfigurationKind.PROCESS,
            operational_scope=ToolScope.PLANT,
            components=(
                ToolComponent(
                    key='main',
                    display_name='Main',
                    subcomponents=(ToolSubcomponent(key='motor', display_name='Motor'),),
                ),
            ),
        )
        return ToolDependencyEntry(
            tool_key=key,
            display_name=key.title(),
            source_release_id=f'release-{key}',
            kind=ToolConfigurationKind.PROCESS,
            structure=structure,
        )

    manifest = ToolDependencyManifest(
        confirmed_tool_catalog_revision='catalog-1',
        tools=(entry('zeta'), entry('alpha')),
    )
    document = manifest.to_document()

    assert [item['tool_key'] for item in document['tools']] == ['alpha', 'zeta']
    assert ToolDependencyManifest.from_document(document).to_document() == document


def test_source_contracts_preserve_operational_participation_rules():
    consumption = ToolSourceConsumption(tool_key='crusher', source_keys=('pi', 'weather'))
    participation = ToolSourceOperationalParticipation(
        tool_key='crusher',
        control_sources=(
            SourceControlPolicy(
                source_key='pi',
                pre_degrading_after_seconds=30,
                degrading_after_seconds=60,
            ),
        ),
        additional_observation_source_keys=('weather',),
    )

    validate_operational_participation_against_consumption(
        consumption=consumption, participation=participation
    )

    with pytest.raises(ToolSourceOperationalParticipationValidationError):
        validate_operational_participation_against_consumption(
            consumption=ToolSourceConsumption(tool_key='crusher', source_keys=('pi',)),
            participation=participation,
        )


def test_reserved_component_keys_remain_invalid():
    with pytest.raises(ToolConfigurationValidationError):
        ToolStructure(
            tool_key='crusher',
            kind=ToolConfigurationKind.PROCESS,
            operational_scope=ToolScope.PLANT,
            components=(
                ToolComponent(
                    key='global_indicators',
                    display_name='Reserved',
                    subcomponents=(ToolSubcomponent(key='motor', display_name='Motor'),),
                ),
            ),
        )
