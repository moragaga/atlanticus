from types import MappingProxyType

import pytest

from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.configuration.tools import (
    ToolConfiguration,
    ToolConfigurationKind,
    ToolConfigurationValidationError,
)


def _configuration(
    *,
    tool_key: str = 'process',
    source_keys: tuple[str, ...] = ('pi',),
    control_sources: tuple[SourceControlPolicy, ...] = (SourceControlPolicy('pi', 200, 300),),
    additional_observation_source_keys: tuple[str, ...] = (),
) -> ToolConfiguration:
    return ToolConfiguration(
        tool_key=tool_key,
        display_name='Process',
        kind=ToolConfigurationKind.PROCESS,
        source_consumption=ToolSourceConsumption(
            tool_key=tool_key,
            source_keys=source_keys,
        ),
        source_operational_participation=ToolSourceOperationalParticipation(
            tool_key=tool_key,
            control_sources=control_sources,
            additional_observation_source_keys=additional_observation_source_keys,
        ),
    )


def test_configuration_normalizes_identity_and_display_name() -> None:
    configuration = ToolConfiguration(
        tool_key=' Process ',
        display_name=' Process Tool ',
        kind=ToolConfigurationKind.PROCESS,
        source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
        source_operational_participation=ToolSourceOperationalParticipation(
            tool_key='process',
            control_sources=(SourceControlPolicy('pi', 200, 300),),
        ),
    )

    assert configuration.tool_key == 'process'
    assert configuration.display_name == 'Process Tool'


def test_configuration_allows_shape_valid_incomplete_source_draft() -> None:
    configuration = _configuration(source_keys=(), control_sources=())

    assert configuration.source_consumption.source_keys == ()
    assert configuration.source_operational_participation.control_sources == ()


def test_configuration_rejects_source_consumption_for_another_tool() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='source consumption tool key must match',
    ):
        ToolConfiguration(
            tool_key='process',
            display_name='Process',
            kind=ToolConfigurationKind.PROCESS,
            source_consumption=ToolSourceConsumption(
                tool_key='integrated_operations',
                source_keys=('pi',),
            ),
            source_operational_participation=ToolSourceOperationalParticipation(
                tool_key='process',
                control_sources=(SourceControlPolicy('pi', 200, 300),),
            ),
        )


def test_configuration_rejects_operational_participation_for_another_tool() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match='operational participation tool key must match',
    ):
        ToolConfiguration(
            tool_key='process',
            display_name='Process',
            kind=ToolConfigurationKind.PROCESS,
            source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
            source_operational_participation=ToolSourceOperationalParticipation(
                tool_key='integrated_operations',
                control_sources=(SourceControlPolicy('pi', 200, 300),),
            ),
        )


def test_configuration_rejects_participation_outside_consumption() -> None:
    with pytest.raises(
        ToolConfigurationValidationError,
        match="not declared by Tool Source Consumption: 'dispatch'",
    ):
        _configuration(
            source_keys=('pi',),
            control_sources=(
                SourceControlPolicy('pi', 200, 300),
                SourceControlPolicy('dispatch', 400, 600),
            ),
        )


def test_configuration_preserves_additional_observation_contract() -> None:
    configuration = _configuration(
        source_keys=('pi', 'blockgrade'),
        additional_observation_source_keys=('blockgrade',),
    )

    assert configuration.source_operational_participation.effective_observation_source_keys == (
        'pi',
        'blockgrade',
    )


def test_configuration_allows_consumed_source_without_operational_participation() -> None:
    configuration = _configuration(source_keys=('pi', 'future_component_source'))

    assert configuration.source_consumption.consumes('future_component_source') is True
    assert (
        configuration.source_operational_participation.observes('future_component_source') is False
    )


def test_document_roundtrip_preserves_exact_source_contracts() -> None:
    configuration = ToolConfiguration(
        tool_key='integrated_operations',
        display_name='Integrated Operations',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        source_consumption=ToolSourceConsumption(
            tool_key='integrated_operations',
            source_keys=('pi', 'dispatch', 'blockgrade'),
        ),
        source_operational_participation=ToolSourceOperationalParticipation(
            tool_key='integrated_operations',
            control_sources=(
                SourceControlPolicy('pi', 200, 300),
                SourceControlPolicy('dispatch', 400, 600),
            ),
            additional_observation_source_keys=('blockgrade',),
        ),
    )

    restored = ToolConfiguration.from_document(MappingProxyType(configuration.to_document()))

    assert restored == configuration


def test_document_shape_keeps_data003_and_data004_explicit() -> None:
    document = _configuration().to_document()

    assert tuple(document) == (
        'tool_key',
        'display_name',
        'kind',
        'source_consumption',
        'source_operational_participation',
    )
    assert document['source_consumption'] == {
        'tool_key': 'process',
        'source_keys': ['pi'],
    }
    assert document['source_operational_participation'] == {
        'tool_key': 'process',
        'control_sources': [
            {
                'source_key': 'pi',
                'pre_degrading_after_seconds': 200,
                'degrading_after_seconds': 300,
            }
        ],
        'additional_observation_source_keys': [],
    }


def test_document_reader_rejects_invalid_shape() -> None:
    with pytest.raises(ToolConfigurationValidationError, match='contract is invalid'):
        ToolConfiguration.from_document({'tool_key': 'process'})


def test_configuration_rejects_invalid_tool_key() -> None:
    with pytest.raises(ToolConfigurationValidationError, match='Tool key has an invalid format'):
        ToolConfiguration(
            tool_key='process tool',
            display_name='Process',
            kind=ToolConfigurationKind.PROCESS,
            source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
            source_operational_participation=ToolSourceOperationalParticipation(
                tool_key='process',
                control_sources=(SourceControlPolicy('pi', 200, 300),),
            ),
        )


def test_configuration_rejects_empty_display_name() -> None:
    with pytest.raises(ToolConfigurationValidationError, match='display name must not be empty'):
        ToolConfiguration(
            tool_key='process',
            display_name=' ',
            kind=ToolConfigurationKind.PROCESS,
            source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
            source_operational_participation=ToolSourceOperationalParticipation(
                tool_key='process',
                control_sources=(SourceControlPolicy('pi', 200, 300),),
            ),
        )


def test_configuration_rejects_invalid_kind_type() -> None:
    with pytest.raises(ToolConfigurationValidationError, match='Tool kind is invalid'):
        ToolConfiguration(
            tool_key='process',
            display_name='Process',
            kind='process',  # type: ignore[arg-type]
            source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
            source_operational_participation=ToolSourceOperationalParticipation(
                tool_key='process',
                control_sources=(SourceControlPolicy('pi', 200, 300),),
            ),
        )
