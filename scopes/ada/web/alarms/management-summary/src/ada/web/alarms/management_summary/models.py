from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from .errors import AlarmManagementSummaryDefinitionError


class AlarmManagementSummaryArea(StrEnum):
    MINE = 'mine'
    PLANT = 'plant'


class AlarmManagementSummaryTone(StrEnum):
    NEUTRAL = 'neutral'
    ATTENTION = 'attention'
    CRITICAL = 'critical'


@dataclass(frozen=True, slots=True)
class AlarmManagementSummarySegmentState:
    area: AlarmManagementSummaryArea
    group: int
    management_percentage: float
    tone: AlarmManagementSummaryTone = AlarmManagementSummaryTone.NEUTRAL

    def __post_init__(self) -> None:
        if (
            isinstance(self.group, bool)
            or not isinstance(self.group, int)
            or not 1 <= self.group <= 4
        ):
            raise AlarmManagementSummaryDefinitionError(
                'Alarm management summary group must be an integer between 1 and 4'
            )
        if not 0 <= self.management_percentage <= 100:
            raise AlarmManagementSummaryDefinitionError(
                'Alarm management summary percentage must be between 0 and 100'
            )


@dataclass(frozen=True, slots=True)
class AlarmManagementSummaryState:
    segments: tuple[AlarmManagementSummarySegmentState, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'segments', tuple(self.segments))
        if not self.segments:
            raise AlarmManagementSummaryDefinitionError(
                'Alarm management summary requires at least one segment'
            )
        areas = [segment.area for segment in self.segments]
        if len(areas) != len(set(areas)):
            raise AlarmManagementSummaryDefinitionError(
                'Alarm management summary contains duplicate areas'
            )

    @classmethod
    def from_iterable(
        cls,
        segments: Iterable[AlarmManagementSummarySegmentState],
    ) -> AlarmManagementSummaryState:
        return cls(segments=tuple(segments))
