import inspect

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
    validate_ada_operational_tool_sources,
)


def _configuration(
    *,
    source_keys: tuple[str, ...],
    control_sources: tuple[SourceControlPolicy, ...],
    additional_observation_source_keys: tuple[str, ...] = (),
) -> ToolConfiguration:
    return ToolConfiguration(
        tool_key='process',
        display_name='Process',
        kind=ToolConfigurationKind.PROCESS,
        source_consumption=ToolSourceConsumption(
            tool_key='process',
            source_keys=source_keys,
        ),
        source_operational_participation=ToolSourceOperationalParticipation(
            tool_key='process',
            control_sources=control_sources,
            additional_observation_source_keys=additional_observation_source_keys,
        ),
    )


def test_operational_validation_accepts_pi_only_tool() -> None:
    configuration = _configuration(
        source_keys=('pi',),
        control_sources=(SourceControlPolicy('pi', 200, 300),),
    )

    validate_ada_operational_tool_sources(configuration)


def test_operational_validation_accepts_pi_and_dispatch_control() -> None:
    configuration = _configuration(
        source_keys=('pi', 'dispatch'),
        control_sources=(
            SourceControlPolicy('pi', 200, 300),
            SourceControlPolicy('dispatch', 400, 600),
        ),
    )

    validate_ada_operational_tool_sources(configuration)


def test_operational_validation_accepts_additional_observation() -> None:
    configuration = _configuration(
        source_keys=('pi', 'blockgrade'),
        control_sources=(SourceControlPolicy('pi', 200, 300),),
        additional_observation_source_keys=('blockgrade',),
    )

    validate_ada_operational_tool_sources(configuration)


def test_operational_validation_requires_explicit_pi_consumption() -> None:
    configuration = _configuration(source_keys=(), control_sources=())

    with pytest.raises(
        ToolConfigurationValidationError,
        match='requires PI source consumption',
    ):
        validate_ada_operational_tool_sources(configuration)


def test_operational_validation_requires_pi_control() -> None:
    configuration = _configuration(source_keys=('pi',), control_sources=())

    with pytest.raises(
        ToolConfigurationValidationError,
        match='requires PI as a CONTROL source',
    ):
        validate_ada_operational_tool_sources(configuration)


def test_operational_validation_requires_dispatch_control_when_consumed() -> None:
    configuration = _configuration(
        source_keys=('pi', 'dispatch'),
        control_sources=(SourceControlPolicy('pi', 200, 300),),
    )

    with pytest.raises(
        ToolConfigurationValidationError,
        match='Dispatch declared by Tool Source Consumption must participate as CONTROL',
    ):
        validate_ada_operational_tool_sources(configuration)


def test_operational_validation_rejects_non_ada_control_source() -> None:
    configuration = _configuration(
        source_keys=('pi', 'future_control'),
        control_sources=(
            SourceControlPolicy('pi', 200, 300),
            SourceControlPolicy('future_control', 400, 600),
        ),
    )

    with pytest.raises(
        ToolConfigurationValidationError,
        match="supports only PI and Dispatch as CONTROL sources: 'future_control'",
    ):
        validate_ada_operational_tool_sources(configuration)


def test_operational_validation_does_not_restrict_additional_observation_names() -> None:
    configuration = _configuration(
        source_keys=('pi', 'future_observation'),
        control_sources=(SourceControlPolicy('pi', 200, 300),),
        additional_observation_source_keys=('future_observation',),
    )

    validate_ada_operational_tool_sources(configuration)


def test_tool_configuration_contract_has_no_structure_or_ui_fields_yet() -> None:
    fields = ToolConfiguration.__dataclass_fields__

    assert tuple(fields) == (
        'tool_key',
        'display_name',
        'kind',
        'source_consumption',
        'source_operational_participation',
    )
    for field in (
        'components',
        'subcomponents',
        'layout_role',
        'alarm_points',
        'renderer',
        'show_in_summary',
    ):
        assert field not in fields


def test_tool_configuration_source_has_no_transport_or_implementation_details() -> None:
    import ada.configuration.tools.models as models

    source = inspect.getsource(models).casefold()

    for forbidden in (
        'cosmos',
        'sharepoint',
        'endpoint',
        'callback',
        'renderer',
        'container_name',
        'query',
    ):
        assert forbidden not in source


def test_tool_configuration_reuses_data003_and_data004_contract_types() -> None:
    fields = ToolConfiguration.__dataclass_fields__

    assert fields['source_consumption'].type == 'ToolSourceConsumption'
    assert fields['source_operational_participation'].type == ('ToolSourceOperationalParticipation')
