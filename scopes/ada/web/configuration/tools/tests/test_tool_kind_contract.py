from types import MappingProxyType

import pytest

from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.configuration.tools import (
    ToolComponent,
    ToolConfiguration,
    ToolConfigurationKind,
    ToolConfigurationValidationError,
    ToolStructure,
)


def _strategic_structure() -> ToolStructure:
    return ToolStructure(
        tool_key='strategic',
        kind=ToolConfigurationKind.STRATEGIC,
        components=(
            ToolComponent(
                key='overview',
                display_name='Overview',
            ),
        ),
    )


def test_strategic_kind_is_stable_string_contract() -> None:
    assert ToolConfigurationKind.STRATEGIC.value == 'strategic'
    assert ToolConfigurationKind('strategic') is ToolConfigurationKind.STRATEGIC


def test_strategic_structure_uses_common_contract_and_roundtrips() -> None:
    structure = _strategic_structure()

    restored = ToolStructure.from_document(MappingProxyType(structure.to_document()))

    assert restored == structure
    assert restored.kind is ToolConfigurationKind.STRATEGIC
    assert restored.components[0].key == 'overview'


def test_tool_configuration_roundtrip_preserves_strategic_kind() -> None:
    structure = _strategic_structure()
    configuration = ToolConfiguration(
        tool_key='strategic',
        display_name='Strategic',
        kind=ToolConfigurationKind.STRATEGIC,
        source_consumption=ToolSourceConsumption(
            tool_key='strategic',
            source_keys=('pi',),
        ),
        source_operational_participation=ToolSourceOperationalParticipation(
            tool_key='strategic',
            control_sources=(SourceControlPolicy('pi', 200, 300),),
        ),
        structure=structure,
    )

    restored = ToolConfiguration.from_document(
        MappingProxyType(configuration.to_document())
    )

    assert restored == configuration
    assert restored.kind is ToolConfigurationKind.STRATEGIC
    assert restored.structure == structure


def test_strategic_does_not_inherit_existing_alarm_projection_policy() -> None:
    structure = _strategic_structure()

    with pytest.raises(
        ToolConfigurationValidationError,
        match='Alarm projection is not defined for Strategic Tool Structure',
    ):
        _ = structure.alarm_baseline_component_keys

    with pytest.raises(
        ToolConfigurationValidationError,
        match='Alarm projection is not defined for Strategic Tool Structure',
    ):
        _ = structure.alarm_subcomponent_addresses

    with pytest.raises(
        ToolConfigurationValidationError,
        match='Alarm projection is not defined for Strategic Tool Structure',
    ):
        structure.alarm_subcomponent_addresses_for_component('overview')
