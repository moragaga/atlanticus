import pytest

from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.configuration.tools import ToolConfiguration, ToolConfigurationKind
from ada.web.configuration.tool_editor import (
    ToolSourceEditorValidationError,
    ToolSourceEditorValues,
    build_configuration_from_source_editor,
    parse_additional_observation_source_keys,
    source_editor_values_from_configuration,
)


def _configuration(
    *,
    dispatch: bool = True,
    additional: tuple[str, ...] = ('blockgrade',),
) -> ToolConfiguration:
    controls = [
        SourceControlPolicy(
            source_key='pi',
            pre_degrading_after_seconds=200,
            degrading_after_seconds=300,
        )
    ]
    sources = ['pi']
    if dispatch:
        controls.append(
            SourceControlPolicy(
                source_key='dispatch',
                pre_degrading_after_seconds=400,
                degrading_after_seconds=600,
            )
        )
        sources.append('dispatch')
    sources.extend(additional)
    return ToolConfiguration(
        tool_key='process',
        display_name='Process',
        kind=ToolConfigurationKind.PROCESS,
        source_consumption=ToolSourceConsumption(
            tool_key='process',
            source_keys=tuple(sources),
        ),
        source_operational_participation=ToolSourceOperationalParticipation(
            tool_key='process',
            control_sources=tuple(controls),
            additional_observation_source_keys=additional,
        ),
    )


def test_editor_values_load_control_thresholds_and_observations() -> None:
    values = source_editor_values_from_configuration(_configuration())

    assert values.pi_pre_degrading_after_seconds == 200
    assert values.pi_degrading_after_seconds == 300
    assert values.dispatch_enabled is True
    assert values.dispatch_pre_degrading_after_seconds == 400
    assert values.dispatch_degrading_after_seconds == 600
    assert values.additional_observation_source_keys == ('blockgrade',)


def test_editor_values_allow_tool_without_dispatch_or_additional_sources() -> None:
    values = source_editor_values_from_configuration(_configuration(dispatch=False, additional=()))

    assert values.dispatch_enabled is False
    assert values.dispatch_pre_degrading_after_seconds is None
    assert values.dispatch_degrading_after_seconds is None
    assert values.additional_observation_source_keys == ()


def test_editor_values_allow_incomplete_draft_configuration() -> None:
    configuration = ToolConfiguration(
        tool_key='process',
        display_name='Process',
        kind=ToolConfigurationKind.PROCESS,
        source_consumption=ToolSourceConsumption(tool_key='process'),
        source_operational_participation=ToolSourceOperationalParticipation(tool_key='process'),
    )

    values = source_editor_values_from_configuration(configuration)

    assert values.pi_pre_degrading_after_seconds is None
    assert values.pi_degrading_after_seconds is None
    assert values.dispatch_enabled is False


def test_parse_additional_observations_accepts_lines_and_commas() -> None:
    assert parse_additional_observation_source_keys(' blockgrade\nGeology, maintenance_state ') == (
        'blockgrade',
        'geology',
        'maintenance_state',
    )


def test_parse_additional_observations_deduplicates_preserving_order() -> None:
    assert parse_additional_observation_source_keys('geology, blockgrade, geology') == (
        'geology',
        'blockgrade',
    )


def test_parse_additional_observations_ignores_empty_entries() -> None:
    assert parse_additional_observation_source_keys(' , \n blockgrade,') == ('blockgrade',)


@pytest.mark.parametrize('source_key', ['pi', 'dispatch'])
def test_parse_additional_observations_rejects_control_sources(source_key: str) -> None:
    with pytest.raises(
        ToolSourceEditorValidationError,
        match='must not duplicate CONTROL source',
    ):
        parse_additional_observation_source_keys(source_key)


def test_parse_additional_observations_rejects_invalid_key() -> None:
    with pytest.raises(
        ToolSourceEditorValidationError,
        match='has an invalid format',
    ):
        parse_additional_observation_source_keys('Block Grade')


def test_editor_values_accept_integer_valued_dash_numbers() -> None:
    values = ToolSourceEditorValues(
        pi_pre_degrading_after_seconds=200.0,
        pi_degrading_after_seconds=300.0,
    )

    assert values.pi_pre_degrading_after_seconds == 200
    assert values.pi_degrading_after_seconds == 300


def test_editor_values_reject_non_integer_dash_numbers() -> None:
    with pytest.raises(ToolSourceEditorValidationError, match='must be an integer'):
        ToolSourceEditorValues(
            pi_pre_degrading_after_seconds=200.5,
            pi_degrading_after_seconds=300,
        )


def test_build_configuration_preserves_tool_identity() -> None:
    base = _configuration()
    values = ToolSourceEditorValues(
        pi_pre_degrading_after_seconds=220,
        pi_degrading_after_seconds=330,
    )

    updated = build_configuration_from_source_editor(
        base_configuration=base,
        values=values,
    )

    assert updated.tool_key == base.tool_key
    assert updated.display_name == base.display_name
    assert updated.kind is base.kind


def test_build_configuration_derives_pi_only_consumption() -> None:
    updated = build_configuration_from_source_editor(
        base_configuration=_configuration(),
        values=ToolSourceEditorValues(
            pi_pre_degrading_after_seconds=200,
            pi_degrading_after_seconds=300,
        ),
    )

    assert updated.source_consumption.source_keys == ('pi',)
    assert updated.source_operational_participation.control_source_keys == ('pi',)
    assert updated.source_operational_participation.additional_observation_source_keys == ()


def test_build_configuration_adds_dispatch_control_when_enabled() -> None:
    updated = build_configuration_from_source_editor(
        base_configuration=_configuration(dispatch=False, additional=()),
        values=ToolSourceEditorValues(
            pi_pre_degrading_after_seconds=200,
            pi_degrading_after_seconds=300,
            dispatch_enabled=True,
            dispatch_pre_degrading_after_seconds=400,
            dispatch_degrading_after_seconds=600,
        ),
    )

    assert updated.source_consumption.source_keys == ('pi', 'dispatch')
    assert updated.source_operational_participation.control_source_keys == (
        'pi',
        'dispatch',
    )


def test_build_configuration_adds_additional_observation_to_consumption() -> None:
    updated = build_configuration_from_source_editor(
        base_configuration=_configuration(dispatch=False, additional=()),
        values=ToolSourceEditorValues(
            pi_pre_degrading_after_seconds=200,
            pi_degrading_after_seconds=300,
            additional_observation_source_keys=('blockgrade', 'geology'),
        ),
    )

    assert updated.source_consumption.source_keys == ('pi', 'blockgrade', 'geology')
    assert updated.source_operational_participation.effective_observation_source_keys == (
        'pi',
        'blockgrade',
        'geology',
    )


def test_build_configuration_uses_editor_thresholds_as_authority() -> None:
    updated = build_configuration_from_source_editor(
        base_configuration=_configuration(),
        values=ToolSourceEditorValues(
            pi_pre_degrading_after_seconds=250,
            pi_degrading_after_seconds=350,
            dispatch_enabled=True,
            dispatch_pre_degrading_after_seconds=450,
            dispatch_degrading_after_seconds=650,
        ),
    )

    pi_policy = updated.source_operational_participation.control_policy('pi')
    dispatch_policy = updated.source_operational_participation.control_policy('dispatch')
    assert pi_policy is not None
    assert dispatch_policy is not None
    assert pi_policy.pre_degrading_after_seconds == 250
    assert pi_policy.degrading_after_seconds == 350
    assert dispatch_policy.pre_degrading_after_seconds == 450
    assert dispatch_policy.degrading_after_seconds == 650


def test_build_configuration_requires_pi_thresholds() -> None:
    with pytest.raises(
        ToolSourceEditorValidationError,
        match='PI pre-degrading threshold is required',
    ):
        build_configuration_from_source_editor(
            base_configuration=_configuration(),
            values=ToolSourceEditorValues(
                pi_pre_degrading_after_seconds=None,
                pi_degrading_after_seconds=300,
            ),
        )


def test_build_configuration_requires_dispatch_thresholds_when_enabled() -> None:
    with pytest.raises(
        ToolSourceEditorValidationError,
        match='Dispatch pre-degrading threshold is required',
    ):
        build_configuration_from_source_editor(
            base_configuration=_configuration(),
            values=ToolSourceEditorValues(
                pi_pre_degrading_after_seconds=200,
                pi_degrading_after_seconds=300,
                dispatch_enabled=True,
                dispatch_pre_degrading_after_seconds=None,
                dispatch_degrading_after_seconds=600,
            ),
        )
