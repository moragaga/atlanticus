from __future__ import annotations

import pytest

from ada.contracts.tools.sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceConsumptionValidationError,
    ToolSourceOperationalParticipation,
    ToolSourceOperationalParticipationValidationError,
)
from ada.web.content_state import ContentState, ContentStateDependency
from ada.web.operational_state import AdaOperationalState, resolve_ada_operational_state


def _source_configuration(
    *,
    tool_key: str = 'process',
    with_dispatch: bool = False,
    additional_observation_source_keys: tuple[str, ...] = (),
) -> tuple[ToolSourceConsumption, ToolSourceOperationalParticipation]:
    source_keys = ['pi']
    control_sources = [SourceControlPolicy('pi', 200, 300)]
    if with_dispatch:
        source_keys.append('dispatch')
        control_sources.append(SourceControlPolicy('dispatch', 400, 600))
    source_keys.extend(additional_observation_source_keys)
    return (
        ToolSourceConsumption(tool_key=tool_key, source_keys=tuple(source_keys)),
        ToolSourceOperationalParticipation(
            tool_key=tool_key,
            control_sources=tuple(control_sources),
            additional_observation_source_keys=additional_observation_source_keys,
        ),
    )


def test_empty_resolution_is_explicit_and_ready() -> None:
    state = resolve_ada_operational_state(has_global_indicators=False)

    assert state == AdaOperationalState(
        tool_key=None,
        global_indicators_runtime_state=ContentState.READY,
        global_indicators_source_keys=(),
    )


def test_source_configuration_preserves_tool_identity_without_owning_time_status() -> None:
    consumption, participation = _source_configuration(with_dispatch=True)

    state = resolve_ada_operational_state(
        has_global_indicators=False,
        source_consumption=consumption,
        source_operational_participation=participation,
    )

    assert state.tool_key == 'process'
    assert state.global_indicators_runtime_state is ContentState.READY


def test_content_state_dependencies_are_client_driven_and_start_ready() -> None:
    consumption, participation = _source_configuration()

    state = resolve_ada_operational_state(
        has_global_indicators=True,
        content_state_dependencies=(
            ContentStateDependency(component_key='global_indicators', source_keys=('pi',)),
        ),
        source_consumption=consumption,
        source_operational_participation=participation,
    )

    assert state.global_indicators_runtime_state is ContentState.READY
    assert state.global_indicators_source_keys == ('pi',)


def test_additional_observation_does_not_become_control_dependency() -> None:
    consumption, participation = _source_configuration(
        additional_observation_source_keys=('blockgrade',)
    )

    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match="not declared as CONTROL: 'blockgrade'",
    ):
        resolve_ada_operational_state(
            has_global_indicators=True,
            content_state_dependencies=(
                ContentStateDependency(
                    component_key='global_indicators',
                    source_keys=('blockgrade',),
                ),
            ),
            source_consumption=consumption,
            source_operational_participation=participation,
        )


def test_dependency_source_must_be_declared_by_tool_consumption() -> None:
    consumption, participation = _source_configuration()

    with pytest.raises(
        ToolSourceConsumptionValidationError,
        match="Source is not declared by Tool Configuration: 'dispatch'",
    ):
        resolve_ada_operational_state(
            has_global_indicators=True,
            content_state_dependencies=(
                ContentStateDependency(
                    component_key='global_indicators',
                    source_keys=('pi', 'dispatch'),
                ),
            ),
            source_consumption=consumption,
            source_operational_participation=participation,
        )


def test_source_driven_resolution_requires_consumption_and_participation() -> None:
    dependency = (ContentStateDependency(component_key='global_indicators', source_keys=('pi',)),)

    with pytest.raises(
        ToolSourceConsumptionValidationError,
        match='requires ToolSourceConsumption',
    ):
        resolve_ada_operational_state(
            has_global_indicators=True,
            content_state_dependencies=dependency,
        )

    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='requires ToolSourceOperationalParticipation',
    ):
        resolve_ada_operational_state(
            has_global_indicators=True,
            content_state_dependencies=dependency,
            source_consumption=ToolSourceConsumption(tool_key='process', source_keys=('pi',)),
        )


def test_participation_without_consumption_is_invalid_even_without_dependencies() -> None:
    with pytest.raises(
        ToolSourceConsumptionValidationError,
        match='requires ToolSourceConsumption',
    ):
        resolve_ada_operational_state(
            has_global_indicators=False,
            source_operational_participation=ToolSourceOperationalParticipation(
                tool_key='process',
                control_sources=(SourceControlPolicy('pi', 200, 300),),
            ),
        )


def test_only_global_indicators_is_supported_by_current_content_state_contract() -> None:
    with pytest.raises(ValueError, match='Unsupported Generic Application Content State component'):
        resolve_ada_operational_state(
            has_global_indicators=False,
            content_state_dependencies=(
                ContentStateDependency(component_key='other_component', source_keys=('pi',)),
            ),
        )


def test_global_indicator_dependency_requires_component_existence() -> None:
    with pytest.raises(ValueError, match='requires Global Indicators'):
        resolve_ada_operational_state(
            has_global_indicators=False,
            content_state_dependencies=(
                ContentStateDependency(component_key='global_indicators', source_keys=('pi',)),
            ),
        )


def test_operational_state_package_has_no_dash_or_time_status_runtime_dependency() -> None:
    from pathlib import Path

    source = (
        Path(__file__).parents[1] / 'src' / 'ada' / 'web' / 'operational_state' / 'resolver.py'
    ).read_text(encoding='utf-8')

    assert 'from dash' not in source
    assert 'import dash' not in source
    assert 'time_status' not in source
    assert 'requests' not in source
    assert 'httpx' not in source
    assert 'cosmos' not in source.lower()
    assert 'filesystem' not in source.lower()
