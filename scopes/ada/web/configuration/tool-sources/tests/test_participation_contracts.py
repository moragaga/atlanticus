import pytest

from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
    ToolSourceOperationalParticipationValidationError,
    validate_operational_participation_against_consumption,
)


def test_validation_accepts_control_and_additional_observation_declared_by_consumption() -> None:
    consumption = ToolSourceConsumption(
        tool_key='integrated_operations',
        source_keys=('pi', 'dispatch', 'blockgrade'),
    )
    participation = ToolSourceOperationalParticipation(
        tool_key='integrated_operations',
        control_sources=(
            SourceControlPolicy('pi', 200, 300),
            SourceControlPolicy('dispatch', 400, 600),
        ),
        additional_observation_source_keys=('blockgrade',),
    )

    validate_operational_participation_against_consumption(
        consumption=consumption,
        participation=participation,
    )


def test_validation_accepts_tool_without_additional_observation_sources() -> None:
    consumption = ToolSourceConsumption(tool_key='process', source_keys=('pi',))
    participation = ToolSourceOperationalParticipation(
        tool_key='process',
        control_sources=(SourceControlPolicy('pi', 200, 300),),
    )

    validate_operational_participation_against_consumption(
        consumption=consumption,
        participation=participation,
    )


def test_validation_rejects_different_tool_identity() -> None:
    consumption = ToolSourceConsumption(tool_key='process', source_keys=('pi',))
    participation = ToolSourceOperationalParticipation(
        tool_key='integrated_operations',
        control_sources=(SourceControlPolicy('pi', 200, 300),),
    )

    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='tool key must match',
    ):
        validate_operational_participation_against_consumption(
            consumption=consumption,
            participation=participation,
        )


def test_validation_rejects_control_source_not_declared_by_consumption() -> None:
    consumption = ToolSourceConsumption(tool_key='process', source_keys=('pi',))
    participation = ToolSourceOperationalParticipation(
        tool_key='process',
        control_sources=(
            SourceControlPolicy('pi', 200, 300),
            SourceControlPolicy('dispatch', 400, 600),
        ),
    )

    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match="Source is not declared.*'dispatch'",
    ):
        validate_operational_participation_against_consumption(
            consumption=consumption,
            participation=participation,
        )


def test_validation_rejects_additional_observation_not_declared_by_consumption() -> None:
    consumption = ToolSourceConsumption(tool_key='process', source_keys=('pi',))
    participation = ToolSourceOperationalParticipation(
        tool_key='process',
        control_sources=(SourceControlPolicy('pi', 200, 300),),
        additional_observation_source_keys=('blockgrade',),
    )

    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match="Source is not declared.*'blockgrade'",
    ):
        validate_operational_participation_against_consumption(
            consumption=consumption,
            participation=participation,
        )


def test_contract_does_not_require_named_source_catalog() -> None:
    consumption = ToolSourceConsumption(
        tool_key='future_tool',
        source_keys=('future_control', 'future_observation'),
    )
    participation = ToolSourceOperationalParticipation(
        tool_key='future_tool',
        control_sources=(SourceControlPolicy('future_control', 10, 20),),
        additional_observation_source_keys=('future_observation',),
    )

    validate_operational_participation_against_consumption(
        consumption=consumption,
        participation=participation,
    )
