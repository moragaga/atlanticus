from __future__ import annotations

from dataclasses import dataclass

from ada.contracts.tools.sources import (
    ToolSourceConsumption,
    ToolSourceConsumptionValidationError,
    ToolSourceOperationalParticipation,
    ToolSourceOperationalParticipationValidationError,
    validate_operational_participation_against_consumption,
)
from ada.web.ui.time_status import TimeStatusDetailState

_SUPPORTED_CONTROL_SOURCE_KEYS = frozenset({'pi', 'dispatch'})


@dataclass(frozen=True, slots=True)
class TimeStatusRuntimeBinding:
    consumption: ToolSourceConsumption
    participation: ToolSourceOperationalParticipation
    detail: TimeStatusDetailState | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.consumption, ToolSourceConsumption):
            raise TypeError('consumption must be ToolSourceConsumption')
        if not isinstance(self.participation, ToolSourceOperationalParticipation):
            raise TypeError('participation must be ToolSourceOperationalParticipation')
        if self.detail is not None and not isinstance(self.detail, TimeStatusDetailState):
            raise TypeError('detail must be TimeStatusDetailState or None')
        validate_operational_participation_against_consumption(
            consumption=self.consumption,
            participation=self.participation,
        )
        self._validate_control_sources()
        self._validate_detail_sources()

    @property
    def tool_key(self) -> str:
        return self.consumption.tool_key

    def _validate_control_sources(self) -> None:
        if not self.consumption.consumes('pi'):
            raise ToolSourceConsumptionValidationError(
                "Source is not declared by Tool Configuration: 'pi'"
            )
        if not self.participation.controls('pi'):
            raise ToolSourceOperationalParticipationValidationError(
                'ADA Time Status requires PI as a CONTROL source'
            )
        unsupported = tuple(
            source_key
            for source_key in self.participation.control_source_keys
            if source_key not in _SUPPORTED_CONTROL_SOURCE_KEYS
        )
        if unsupported:
            raise ToolSourceOperationalParticipationValidationError(
                'ADA Time Status supports only PI and Dispatch as CONTROL sources: '
                f'{unsupported[0]!r}'
            )
        if self.consumption.consumes('dispatch') and not self.participation.controls('dispatch'):
            raise ToolSourceOperationalParticipationValidationError(
                'Dispatch declared by Tool Source Consumption must participate as CONTROL'
            )

    def _validate_detail_sources(self) -> None:
        if self.detail is None:
            return
        additional = set(self.participation.additional_observation_source_keys)
        for source in self.detail.sources:
            if not self.consumption.consumes(source.key):
                raise ToolSourceConsumptionValidationError(
                    f'Source is not declared by Tool Configuration: {source.key!r}'
                )
            if source.key not in additional:
                raise ToolSourceOperationalParticipationValidationError(
                    'Time Status detail source is not declared as ADDITIONAL OBSERVATION: '
                    f'{source.key!r}'
                )
