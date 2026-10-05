import pytest

from ada.contracts.tools import (
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
        center_component_key='main',
        components=(
            ToolComponent(
                key='main',
                display_name='Main',
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
        'center_component_key': 'main',
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
                        linked_component_keys=('mine_peer',),
                    ),
                ),
            ),
            ToolComponent(
                key='mine_peer',
                display_name='Mine Peer',
                scope=ToolScope.MINE,
                subcomponents=(
                    ToolSubcomponent(
                        key='local',
                        display_name='Local',
                    ),
                ),
            ),
            ToolComponent(
                key='plant',
                display_name='Plant',
                scope=ToolScope.PLANT,
                subcomponents=(ToolSubcomponent(key='local', display_name='Local'),),
            ),
        ),
    )

    assert (
        structure.subcomponent_address(
            component_key='mine_peer', subcomponent_key='shared'
        ).owner_component_key
        == 'mine'
    )


def test_manifest_roundtrip_and_order_are_stable():
    def entry(key):
        structure = ToolStructure(
            tool_key=key,
            kind=ToolConfigurationKind.PROCESS,
            operational_scope=ToolScope.PLANT,
            center_component_key='main',
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


def test_process_requires_explicit_existing_center_component() -> None:
    component = ToolComponent(
        key='main',
        display_name='Main',
        subcomponents=(ToolSubcomponent(key='motor', display_name='Motor'),),
    )

    with pytest.raises(ToolConfigurationValidationError, match='requires center component key'):
        ToolStructure(
            tool_key='crusher',
            kind=ToolConfigurationKind.PROCESS,
            operational_scope=ToolScope.PLANT,
            components=(component,),
        )

    with pytest.raises(ToolConfigurationValidationError, match='existing component'):
        ToolStructure(
            tool_key='crusher',
            kind=ToolConfigurationKind.PROCESS,
            operational_scope=ToolScope.PLANT,
            center_component_key='missing',
            components=(component,),
        )


def test_integrated_operations_preserves_operational_order() -> None:
    structure = ToolStructure(
        tool_key='integrated',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                key='mine_a',
                display_name='Mine A',
                scope=ToolScope.MINE,
                subcomponents=(ToolSubcomponent(key='a', display_name='A'),),
            ),
            ToolComponent(
                key='mine_b',
                display_name='Mine B',
                scope=ToolScope.MINE,
                subcomponents=(ToolSubcomponent(key='b', display_name='B'),),
            ),
            ToolComponent(
                key='plant_a',
                display_name='Plant A',
                scope=ToolScope.PLANT,
                subcomponents=(ToolSubcomponent(key='c', display_name='C'),),
            ),
        ),
    )

    restored = ToolStructure.from_document(structure.to_document())

    assert tuple(component.key for component in restored.components) == (
        'mine_a',
        'mine_b',
        'plant_a',
    )


def test_integrated_operations_rejects_incomplete_or_reversed_scope_sequence() -> None:
    def component(key: str, scope: ToolScope) -> ToolComponent:
        return ToolComponent(
            key=key,
            display_name=key,
            scope=scope,
            subcomponents=(ToolSubcomponent(key=f'{key}_sub', display_name='Sub'),),
        )

    with pytest.raises(ToolConfigurationValidationError, match='requires Mine and Plant'):
        ToolStructure(
            tool_key='integrated',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(component('mine', ToolScope.MINE),),
        )

    with pytest.raises(ToolConfigurationValidationError, match='Mine-to-Plant operational order'):
        ToolStructure(
            tool_key='integrated',
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            components=(
                component('mine_a', ToolScope.MINE),
                component('plant', ToolScope.PLANT),
                component('mine_b', ToolScope.MINE),
            ),
        )
