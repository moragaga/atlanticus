from types import MappingProxyType

import pytest

from ada.configuration.tool_sources import (
    SourceControlPolicy,
    ToolSourceOperationalParticipation,
    ToolSourceOperationalParticipationValidationError,
)


def test_control_policy_normalizes_source_key() -> None:
    policy = SourceControlPolicy(
        source_key=' PI ',
        pre_degrading_after_seconds=200,
        degrading_after_seconds=300,
    )

    assert policy.source_key == 'pi'


def test_control_policy_preserves_thresholds() -> None:
    policy = SourceControlPolicy(
        source_key='dispatch',
        pre_degrading_after_seconds=400,
        degrading_after_seconds=600,
    )

    assert policy.pre_degrading_after_seconds == 400
    assert policy.degrading_after_seconds == 600


def test_control_policy_rejects_invalid_source_key() -> None:
    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='Source key has an invalid format',
    ):
        SourceControlPolicy(
            source_key='invalid source',
            pre_degrading_after_seconds=200,
            degrading_after_seconds=300,
        )


def test_control_policy_rejects_non_integer_thresholds() -> None:
    for value in (True, 1.5, '200'):
        with pytest.raises(
            ToolSourceOperationalParticipationValidationError,
            match='must be an integer',
        ):
            SourceControlPolicy(
                source_key='pi',
                pre_degrading_after_seconds=value,  # type: ignore[arg-type]
                degrading_after_seconds=300,
            )


def test_control_policy_rejects_non_positive_thresholds() -> None:
    for value in (0, -1):
        with pytest.raises(
            ToolSourceOperationalParticipationValidationError,
            match='must be greater than zero',
        ):
            SourceControlPolicy(
                source_key='pi',
                pre_degrading_after_seconds=value,
                degrading_after_seconds=300,
            )


def test_control_policy_requires_pre_degrading_before_degrading() -> None:
    for pre_degrading, degrading in ((300, 300), (301, 300)):
        with pytest.raises(
            ToolSourceOperationalParticipationValidationError,
            match='must be lower than degrading threshold',
        ):
            SourceControlPolicy(
                source_key='pi',
                pre_degrading_after_seconds=pre_degrading,
                degrading_after_seconds=degrading,
            )


def test_control_policy_document_roundtrip() -> None:
    policy = SourceControlPolicy(
        source_key='pi',
        pre_degrading_after_seconds=200,
        degrading_after_seconds=300,
    )

    restored = SourceControlPolicy.from_document(MappingProxyType(policy.to_document()))

    assert restored == policy


def test_participation_normalizes_identity_and_preserves_order() -> None:
    participation = ToolSourceOperationalParticipation(
        tool_key=' Integrated_Operations ',
        control_sources=(
            SourceControlPolicy(' PI ', 200, 300),
            SourceControlPolicy('Dispatch', 400, 600),
        ),
        additional_observation_source_keys=(' BlockGrade ', 'geology'),
    )

    assert participation.tool_key == 'integrated_operations'
    assert participation.control_source_keys == ('pi', 'dispatch')
    assert participation.additional_observation_source_keys == ('blockgrade', 'geology')


def test_participation_allows_no_additional_observations() -> None:
    participation = ToolSourceOperationalParticipation(
        tool_key='process',
        control_sources=(SourceControlPolicy('pi', 200, 300),),
    )

    assert participation.additional_observation_source_keys == ()
    assert participation.effective_observation_source_keys == ('pi',)


def test_effective_observation_is_control_union_additional_observation() -> None:
    participation = ToolSourceOperationalParticipation(
        tool_key='integrated_operations',
        control_sources=(
            SourceControlPolicy('pi', 200, 300),
            SourceControlPolicy('dispatch', 400, 600),
        ),
        additional_observation_source_keys=('blockgrade',),
    )

    assert participation.effective_observation_source_keys == (
        'pi',
        'dispatch',
        'blockgrade',
    )


def test_participation_supports_future_source_without_global_catalog() -> None:
    participation = ToolSourceOperationalParticipation(
        tool_key='future_tool',
        additional_observation_source_keys=('future_source_2',),
    )

    assert participation.effective_observation_source_keys == ('future_source_2',)


def test_participation_rejects_duplicate_control_sources() -> None:
    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='Control source keys must be unique',
    ):
        ToolSourceOperationalParticipation(
            tool_key='process',
            control_sources=(
                SourceControlPolicy('pi', 200, 300),
                SourceControlPolicy('PI', 400, 600),
            ),
        )


def test_participation_rejects_duplicate_additional_observations() -> None:
    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='Additional observation source keys must be unique',
    ):
        ToolSourceOperationalParticipation(
            tool_key='process',
            additional_observation_source_keys=('blockgrade', ' BlockGrade '),
        )


def test_participation_rejects_redundant_additional_observation_for_control_source() -> None:
    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='must not duplicate control sources',
    ):
        ToolSourceOperationalParticipation(
            tool_key='process',
            control_sources=(SourceControlPolicy('pi', 200, 300),),
            additional_observation_source_keys=('PI',),
        )


def test_participation_rejects_invalid_control_collection() -> None:
    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='must be a collection of source control policies',
    ):
        ToolSourceOperationalParticipation(
            tool_key='process',
            control_sources='pi',  # type: ignore[arg-type]
        )


def test_participation_rejects_non_policy_control_item() -> None:
    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='must contain source control policies',
    ):
        ToolSourceOperationalParticipation(
            tool_key='process',
            control_sources=('pi',),  # type: ignore[arg-type]
        )


def test_participation_rejects_string_as_additional_observation_collection() -> None:
    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='must be a collection of source keys',
    ):
        ToolSourceOperationalParticipation(
            tool_key='process',
            additional_observation_source_keys='blockgrade',  # type: ignore[arg-type]
        )


def test_controls_and_observes_report_effective_participation() -> None:
    participation = ToolSourceOperationalParticipation(
        tool_key='process',
        control_sources=(SourceControlPolicy('pi', 200, 300),),
        additional_observation_source_keys=('blockgrade',),
    )

    assert participation.controls('PI') is True
    assert participation.controls('blockgrade') is False
    assert participation.observes('PI') is True
    assert participation.observes('BLOCKGRADE') is True
    assert participation.observes('dispatch') is False


def test_participation_document_roundtrip_preserves_contract() -> None:
    participation = ToolSourceOperationalParticipation(
        tool_key='integrated_operations',
        control_sources=(
            SourceControlPolicy('pi', 200, 300),
            SourceControlPolicy('dispatch', 400, 600),
        ),
        additional_observation_source_keys=('blockgrade',),
    )

    restored = ToolSourceOperationalParticipation.from_document(participation.to_document())

    assert restored == participation


def test_participation_document_shape_keeps_only_operational_decisions() -> None:
    document = ToolSourceOperationalParticipation(
        tool_key='process',
        control_sources=(SourceControlPolicy('pi', 200, 300),),
        additional_observation_source_keys=('blockgrade',),
    ).to_document()

    assert document == {
        'tool_key': 'process',
        'control_sources': [
            {
                'source_key': 'pi',
                'pre_degrading_after_seconds': 200,
                'degrading_after_seconds': 300,
            }
        ],
        'additional_observation_source_keys': ['blockgrade'],
    }


def test_participation_document_reader_rejects_missing_fields() -> None:
    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='contract is invalid',
    ):
        ToolSourceOperationalParticipation.from_document({'tool_key': 'process'})


def test_control_policy_lookup_returns_policy_or_none() -> None:
    pi = SourceControlPolicy('pi', 200, 300)
    participation = ToolSourceOperationalParticipation(
        tool_key='process',
        control_sources=(pi,),
    )

    assert participation.control_policy('PI') is pi
    assert participation.control_policy('dispatch') is None
