from __future__ import annotations

from collections.abc import Callable
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
class TimeStatusDetailProvider:
    source_keys: tuple[str, ...]
    resolve: Callable[[object], TimeStatusDetailState]

    def __post_init__(self) -> None:
        if not isinstance(self.source_keys, tuple) or not self.source_keys:
            raise ValueError('Time Status provider requires source keys')
        if any(not isinstance(key, str) or not key or key != key.strip() for key in self.source_keys):
            raise ValueError('Time Status provider source key is invalid')
        if len(self.source_keys) != len(set(self.source_keys)):
            raise ValueError('Time Status provider source keys must be unique')
        if not callable(self.resolve):
            raise TypeError('Time Status provider resolve must be callable')


@dataclass(frozen=True, slots=True)
class TimeStatusRuntimeBinding:
    consumption: ToolSourceConsumption
    participation: ToolSourceOperationalParticipation
    detail: TimeStatusDetailState | TimeStatusDetailProvider | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.consumption, ToolSourceConsumption):
            raise TypeError('consumption must be ToolSourceConsumption')
        if not isinstance(self.participation, ToolSourceOperationalParticipation):
            raise TypeError('participation must be ToolSourceOperationalParticipation')
        if self.detail is not None and not isinstance(
            self.detail, TimeStatusDetailState | TimeStatusDetailProvider
        ):
            raise TypeError('detail must be TimeStatusDetailState, TimeStatusDetailProvider or None')
        validate_operational_participation_against_consumption(
            consumption=self.consumption,
            participation=self.participation,
        )
        self._validate_control_sources()
        self._validate_detail_sources()

    @property
    def tool_key(self) -> str:
        return self.consumption.tool_key

    def resolve_detail(self, store_data: object) -> TimeStatusDetailState | None:
        if not isinstance(self.detail, TimeStatusDetailProvider):
            return self.detail
        resolved = self.detail.resolve(store_data)
        if not isinstance(resolved, TimeStatusDetailState):
            raise TypeError('Time Status provider must resolve TimeStatusDetailState')
        if tuple(source.key for source in resolved.sources) != self.detail.source_keys:
            raise ValueError('Time Status provider returned unexpected sources')
        return resolved

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
        source_keys = (
            self.detail.source_keys
            if isinstance(self.detail, TimeStatusDetailProvider)
            else tuple(source.key for source in self.detail.sources)
        )
        additional = set(self.participation.additional_observation_source_keys)
        for source_key in source_keys:
            if not self.consumption.consumes(source_key):
                raise ToolSourceConsumptionValidationError(
                    f'Source is not declared by Tool Configuration: {source_key!r}'
                )
            if source_key not in additional:
                raise ToolSourceOperationalParticipationValidationError(
                    'Time Status detail source is not declared as ADDITIONAL OBSERVATION: '
                    f'{source_key!r}'
                )
