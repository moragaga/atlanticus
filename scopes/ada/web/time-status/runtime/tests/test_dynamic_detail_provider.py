from __future__ import annotations

import pytest

from ada.contracts.tools.sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceConsumptionValidationError,
    ToolSourceOperationalParticipation,
    ToolSourceOperationalParticipationValidationError,
)
from ada.web.time_status.runtime import TimeStatusDetailProvider, TimeStatusRuntimeBinding
from ada.web.ui.time_status import TimeStatusDetailSourceState, TimeStatusDetailState


def _binding(detail, *, consumed_source_keys: tuple[str, ...] = ('pi', 'blockgrade')):
    return TimeStatusRuntimeBinding(
        consumption=ToolSourceConsumption('process', consumed_source_keys),
        participation=ToolSourceOperationalParticipation(
            'process',
            control_sources=(SourceControlPolicy('pi', 200, 300),),
            additional_observation_source_keys=('blockgrade',),
        ),
        detail=detail,
    )


def test_provider_is_validated_against_existing_observation_sources() -> None:
    provider = TimeStatusDetailProvider(
        source_keys=('blockgrade',),
        resolve=lambda _store: TimeStatusDetailState((
            TimeStatusDetailSourceState('blockgrade', 'BlockGrade', 'Sin información'),
        )),
    )
    assert _binding(provider).resolve_detail(None).sources[0].key == 'blockgrade'
    with pytest.raises(
        ToolSourceConsumptionValidationError,
        match='Source is not declared by Tool Configuration',
    ):
        _binding(TimeStatusDetailProvider(('laboratory',), provider.resolve))
    with pytest.raises(
        ToolSourceOperationalParticipationValidationError,
        match='ADDITIONAL OBSERVATION',
    ):
        _binding(
            TimeStatusDetailProvider(('laboratory',), provider.resolve),
            consumed_source_keys=('pi', 'blockgrade', 'laboratory'),
        )


def test_provider_must_return_declared_keys() -> None:
    provider = TimeStatusDetailProvider(
        source_keys=('blockgrade',),
        resolve=lambda _store: TimeStatusDetailState((
            TimeStatusDetailSourceState('other', 'Other', 'Error'),
        )),
    )
    with pytest.raises(ValueError, match='unexpected sources'):
        _binding(provider).resolve_detail(None)
