from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AlarmKind(StrEnum):
    RISK = 'RISK'
    IMPACT = 'IMPACT'


class Criticality(StrEnum):
    C1 = 'C1'
    C2 = 'C2'
    C3 = 'C3'


@dataclass(frozen=True, slots=True, order=True)
class AlarmIdentity:
    family_key: str
    alarm_key: str

    def __post_init__(self) -> None:
        _require_non_empty_string(self.family_key, 'family_key')
        _require_non_empty_string(self.alarm_key, 'alarm_key')

    @property
    def canonical_key(self) -> str:
        return f'{self.family_key}/{self.alarm_key}'


def _require_non_empty_string(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f'{name} must be a string')
    if not value.strip():
        raise ValueError(f'{name} must not be empty')
