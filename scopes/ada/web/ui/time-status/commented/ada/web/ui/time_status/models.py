# Contratos de Time Status: el Summary mantiene PI/Dispatch como fuentes de control y TS-008 agrega filas dinámicas para el Detail.
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from dash.development.base_component import Component

from .errors import TimeStatusDefinitionError

_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')
_DEFAULT_CLOCK_PLACEHOLDER = '----/--/-- --:--:--'
# La autoridad operacional no es configurable: sólo PI y Dispatch pueden actuar como fuentes de control.
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
    # Cada fila recibe sólo identidad, etiqueta y el texto que debe presentar. No interpreta salud ni freshness.
    key: str
    label: str
    value: str

    def __post_init__(self) -> None:
        _require_key(self.key, field_name='detail source key')
        _require_text(self.label, field_name='detail source label')
        _require_text(self.value, field_name='detail source value')

    @property
    def is_control(self) -> bool:
        # Derivar el rol desde la identidad impide que BlockGrade u otra fuente adquiera autoridad por configuración accidental.
        return self.key in _CONTROL_SOURCE_KEYS


@dataclass(frozen=True, slots=True)
class TimeStatusDetailState:
    # Esta secuencia representa exactamente las fuentes que la Tool consume y desea mostrar en el Detail.
    sources: tuple[TimeStatusDetailSourceState, ...]

    def __post_init__(self) -> None:
        sources = tuple(self.sources)
        if not sources:
            raise TimeStatusDefinitionError('Time Status detail requires at least one source')

        keys = tuple(source.key for source in sources)
        if len(keys) != len(set(keys)):
            raise TimeStatusDefinitionError('Time Status detail source keys must be unique')
        if 'pi' not in keys:
            raise TimeStatusDefinitionError("ADA Time Status detail requires PI source key 'pi'")

        # PI y Dispatch ocupan posiciones canónicas. Las fuentes informativas conservan su orden relativo de entrada.
        by_key = {source.key: source for source in sources}
        ordered = [by_key['pi']]
        if 'dispatch' in by_key:
            ordered.append(by_key['dispatch'])
        ordered.extend(source for source in sources if source.key not in _CONTROL_SOURCE_KEYS)
        object.__setattr__(self, 'sources', tuple(ordered))

    @property
    def control_sources(self) -> tuple[TimeStatusDetailSourceState, ...]:
        return tuple(source for source in self.sources if source.is_control)

    @property
    def informational_sources(self) -> tuple[TimeStatusDetailSourceState, ...]:
        return tuple(source for source in self.sources if not source.is_control)

    def to_component(self) -> Component:
        from .presentation import build_time_status_detail

        return build_time_status_detail(state=self)


@dataclass(frozen=True, slots=True)
class TimeStatusSummaryState:
    pi: TimeStatusSourceState
    dispatch: TimeStatusSourceState | None = None
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
