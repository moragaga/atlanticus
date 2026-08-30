# Contratos de Time Status: PI/Dispatch gobiernan la salud superficial; el Detail contiene únicamente fuentes adicionales.
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from dash.development.base_component import Component

from .errors import TimeStatusDefinitionError

_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')
_DEFAULT_CLOCK_PLACEHOLDER = '----/--/-- --:--:--'
# Esta frontera impide duplicar PI/Dispatch dentro del popover y evita que una fuente adicional adquiera autoridad operacional.
_CONTROL_SOURCE_KEYS = frozenset({'pi', 'dispatch'})


class TimeStatusSourceCondition(StrEnum):
    FRESH = 'fresh'
    PREVENTIVE = 'preventive'
    HARD_STALE = 'hard_stale'
    DATA_ERROR = 'data_error'


@dataclass(frozen=True, slots=True)
class TimeStatusFreshnessPolicy:
    warning_after_seconds: int
    stale_after_seconds: int

    def __post_init__(self) -> None:
        if self.warning_after_seconds < 0:
            raise TimeStatusDefinitionError('warning_after_seconds must be non-negative')
        if self.stale_after_seconds <= self.warning_after_seconds:
            raise TimeStatusDefinitionError(
                'stale_after_seconds must be greater than warning_after_seconds'
            )


@dataclass(frozen=True, slots=True)
class TimeStatusSourceState:
    key: str
    label: str
    policy: TimeStatusFreshnessPolicy
    condition: TimeStatusSourceCondition
    relative_age_text: str | None
    timestamp_utc: datetime | None

    def __post_init__(self) -> None:
        _require_key(self.key, field_name='source key')
        _require_text(self.label, field_name='source label')
        if self.timestamp_utc is not None:
            if self.timestamp_utc.tzinfo is None or self.timestamp_utc.utcoffset() is None:
                raise TimeStatusDefinitionError('timestamp_utc must be timezone-aware')
            object.__setattr__(self, 'timestamp_utc', self.timestamp_utc.astimezone(UTC))

        if self.condition is TimeStatusSourceCondition.DATA_ERROR:
            if self.relative_age_text is not None:
                raise TimeStatusDefinitionError('DATA_ERROR source cannot expose relative_age_text')
            return

        if self.timestamp_utc is None:
            raise TimeStatusDefinitionError('Non-error source requires timestamp_utc')
        _require_text(self.relative_age_text, field_name='relative age text')

    @property
    def timestamp_iso(self) -> str | None:
        if self.timestamp_utc is None:
            return None
        return self.timestamp_utc.isoformat().replace('+00:00', 'Z')


@dataclass(frozen=True, slots=True)
class TimeStatusDetailSourceState:
    # Cada fila del Detail representa una fuente adicional ya resuelta por composición; no interpreta freshness.
    key: str
    label: str
    value: str

    def __post_init__(self) -> None:
        _require_key(self.key, field_name='detail source key')
        # PI y Dispatch ya están visibles en el Summary y no pueden repetirse como filas del popover.
        if self.key in _CONTROL_SOURCE_KEYS:
            raise TimeStatusDefinitionError(
                'Time Status detail accepts additional source keys only'
            )
        _require_text(self.label, field_name='detail source label')
        _require_text(self.value, field_name='detail source value')


@dataclass(frozen=True, slots=True)
class TimeStatusDetailState:
    # Cuando existen extras, esta secuencia conserva exactamente su orden de composición.
    sources: tuple[TimeStatusDetailSourceState, ...]

    def __post_init__(self) -> None:
        sources = tuple(self.sources)
        # El caso sin extras se representa con detail=None y has_detail=True para que la Surface muestre su empty-state explícito.
        if not sources:
            raise TimeStatusDefinitionError(
                'Time Status detail requires at least one additional source'
            )

        keys = tuple(source.key for source in sources)
        if len(keys) != len(set(keys)):
            raise TimeStatusDefinitionError('Time Status detail source keys must be unique')
        object.__setattr__(self, 'sources', sources)

    def to_component(self) -> Component:
        from .presentation import build_time_status_detail

        return build_time_status_detail(state=self)


@dataclass(frozen=True, slots=True)
class TimeStatusSummaryState:
    pi: TimeStatusSourceState
    dispatch: TimeStatusSourceState | None = None
    # has_detail significa que PI/Dispatch pueden abrir la Surface, incluso si no existen fuentes adicionales.
    has_detail: bool = False
    current_datetime: str = _DEFAULT_CLOCK_PLACEHOLDER

    def __post_init__(self) -> None:
        if self.pi.key != 'pi':
            raise TimeStatusDefinitionError("ADA Time Status requires PI source key 'pi'")
        if self.dispatch is not None:
            if self.dispatch.key != 'dispatch':
                raise TimeStatusDefinitionError(
                    "ADA Time Status dispatch source key must be 'dispatch'"
                )
            if self.dispatch.key == self.pi.key:
                raise TimeStatusDefinitionError('Time Status source keys must be unique')
        _require_text(self.current_datetime, field_name='current datetime')

    @property
    def required_sources(self) -> tuple[TimeStatusSourceState, ...]:
        if self.dispatch is None:
            return (self.pi,)
        return (self.pi, self.dispatch)

    @property
    def content_stale(self) -> bool:
        return all(
            source.condition is TimeStatusSourceCondition.HARD_STALE
            for source in self.required_sources
        )

    @property
    def data_error_source_keys(self) -> tuple[str, ...]:
        return tuple(
            source.key
            for source in self.required_sources
            if source.condition is TimeStatusSourceCondition.DATA_ERROR
        )

    def to_component(self) -> Component:
        from .presentation import build_time_status_summary

        return build_time_status_summary(state=self)


def _require_key(value: str, *, field_name: str) -> None:
    if not _KEY_PATTERN.fullmatch(value):
        raise TimeStatusDefinitionError(f'Invalid Time Status {field_name}: {value!r}')


def _require_text(value: str | None, *, field_name: str) -> None:
    if value is None or not value.strip():
        raise TimeStatusDefinitionError(f'Time Status {field_name} cannot be empty')
