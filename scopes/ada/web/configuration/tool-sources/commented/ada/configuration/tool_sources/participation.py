from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ada.configuration.tool_sources.errors import (
    ToolSourceOperationalParticipationValidationError,
)

# Las identidades siguen la misma convención neutral definida en DATA-003.
_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


# Política de una fuente que participa en CONTROL para una Tool concreta.
@dataclass(frozen=True, slots=True)
class SourceControlPolicy:
    source_key: str
    pre_degrading_after_seconds: int
    degrading_after_seconds: int

    def __post_init__(self) -> None:
        # Normalizamos identidad y validamos ambos umbrales de forma independiente.
        source_key = _require_key(self.source_key, label='Source key')
        pre_degrading_after_seconds = _require_positive_seconds(
            self.pre_degrading_after_seconds,
            label='Source pre-degrading threshold',
        )
        degrading_after_seconds = _require_positive_seconds(
            self.degrading_after_seconds,
            label='Source degrading threshold',
        )
        # PRE-DEGRADING debe ocurrir estrictamente antes que DEGRADING.
        if pre_degrading_after_seconds >= degrading_after_seconds:
            raise ToolSourceOperationalParticipationValidationError(
                'Source pre-degrading threshold must be lower than degrading threshold'
            )
        object.__setattr__(self, 'source_key', source_key)
        object.__setattr__(
            self,
            'pre_degrading_after_seconds',
            pre_degrading_after_seconds,
        )
        object.__setattr__(self, 'degrading_after_seconds', degrading_after_seconds)

    # Documento estable para persistencia/proyección de Tool Configuration.
    def to_document(self) -> dict[str, object]:
        return {
            'source_key': self.source_key,
            'pre_degrading_after_seconds': self.pre_degrading_after_seconds,
            'degrading_after_seconds': self.degrading_after_seconds,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> SourceControlPolicy:
        try:
            return cls(
                source_key=document['source_key'],
                pre_degrading_after_seconds=document['pre_degrading_after_seconds'],
                degrading_after_seconds=document['degrading_after_seconds'],
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ToolSourceOperationalParticipationValidationError):
                raise
            raise ToolSourceOperationalParticipationValidationError(
                'Source control policy contract is invalid'
            ) from error


# Participación operacional completa de las fuentes de una Tool.
@dataclass(frozen=True, slots=True)
class ToolSourceOperationalParticipation:
    tool_key: str
    control_sources: tuple[SourceControlPolicy, ...] = ()
    additional_observation_source_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        tool_key = _require_key(self.tool_key, label='Tool key')
        control_sources = _require_control_sources(self.control_sources)
        additional_observation_source_keys = _require_source_keys(
            self.additional_observation_source_keys,
            label='Additional observation source keys',
        )
        control_source_keys = tuple(policy.source_key for policy in control_sources)
        # Una fuente CONTROL solo puede aparecer una vez porque cada Tool tiene una política única.
        if len(control_source_keys) != len(set(control_source_keys)):
            raise ToolSourceOperationalParticipationValidationError(
                'Control source keys must be unique'
            )
        overlap = set(control_source_keys).intersection(additional_observation_source_keys)
        # CONTROL ya implica OBSERVATION; repetirla como adicional sería configuración redundante.
        if overlap:
            raise ToolSourceOperationalParticipationValidationError(
                'Additional observation source keys must not duplicate control sources'
            )
        object.__setattr__(self, 'tool_key', tool_key)
        object.__setattr__(self, 'control_sources', control_sources)
        object.__setattr__(
            self,
            'additional_observation_source_keys',
            additional_observation_source_keys,
        )

    @property
    def control_source_keys(self) -> tuple[str, ...]:
        return tuple(policy.source_key for policy in self.control_sources)

    @property
    def effective_observation_source_keys(self) -> tuple[str, ...]:
        # OBSERVATION efectiva se deriva; no se duplica manualmente en Tool Configuration.
        return self.control_source_keys + self.additional_observation_source_keys

    def controls(self, source_key: str) -> bool:
        return _require_key(source_key, label='Source key') in self.control_source_keys

    def control_policy(self, source_key: str) -> SourceControlPolicy | None:
        normalized = _require_key(source_key, label='Source key')
        return next(
            (policy for policy in self.control_sources if policy.source_key == normalized),
            None,
        )

    def observes(self, source_key: str) -> bool:
        normalized = _require_key(source_key, label='Source key')
        return normalized in self.effective_observation_source_keys

    def to_document(self) -> dict[str, object]:
        return {
            'tool_key': self.tool_key,
            'control_sources': [policy.to_document() for policy in self.control_sources],
            'additional_observation_source_keys': list(self.additional_observation_source_keys),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> ToolSourceOperationalParticipation:
        try:
            control_sources = document['control_sources']
            additional_observation_source_keys = document['additional_observation_source_keys']
            if not isinstance(control_sources, list):
                raise TypeError
            if not all(isinstance(item, Mapping) for item in control_sources):
                raise TypeError
            if not isinstance(additional_observation_source_keys, list):
                raise TypeError
            return cls(
                tool_key=document['tool_key'],
                control_sources=tuple(
                    SourceControlPolicy.from_document(item) for item in control_sources
                ),
                additional_observation_source_keys=tuple(additional_observation_source_keys),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ToolSourceOperationalParticipationValidationError):
                raise
            raise ToolSourceOperationalParticipationValidationError(
                'Tool source operational participation contract is invalid'
            ) from error


# Congela una colección de políticas y rechaza elementos que no pertenezcan al contrato.
def _require_control_sources(value: object) -> tuple[SourceControlPolicy, ...]:
    if isinstance(value, (str, bytes)):
        raise ToolSourceOperationalParticipationValidationError(
            'Control sources must be a collection of source control policies'
        )
    try:
        resolved = tuple(iter(value))
    except TypeError as error:
        raise ToolSourceOperationalParticipationValidationError(
            'Control sources must be a collection of source control policies'
        ) from error
    if not all(isinstance(policy, SourceControlPolicy) for policy in resolved):
        raise ToolSourceOperationalParticipationValidationError(
            'Control sources must contain source control policies'
        )
    return resolved


# Normaliza colecciones de source_key sin introducir un catálogo global de fuentes conocidas.
def _require_source_keys(value: object, *, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise ToolSourceOperationalParticipationValidationError(
            f'{label} must be a collection of source keys'
        )
    try:
        source_keys = tuple(
            _require_key(source_key, label='Source key') for source_key in iter(value)
        )
    except TypeError as error:
        raise ToolSourceOperationalParticipationValidationError(
            f'{label} must be a collection of source keys'
        ) from error
    if len(source_keys) != len(set(source_keys)):
        raise ToolSourceOperationalParticipationValidationError(f'{label} must be unique')
    return source_keys


# Los segundos deben ser enteros positivos; bool se rechaza aunque sea subtipo de int en Python.
def _require_positive_seconds(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolSourceOperationalParticipationValidationError(f'{label} must be an integer')
    if value <= 0:
        raise ToolSourceOperationalParticipationValidationError(
            f'{label} must be greater than zero'
        )
    return value


# Normaliza identidades para que documentos y comparaciones sean deterministas.
def _require_key(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise ToolSourceOperationalParticipationValidationError(f'{label} must be a string')
    normalized = value.strip().casefold()
    if not _KEY_PATTERN.fullmatch(normalized):
        raise ToolSourceOperationalParticipationValidationError(f'{label} has an invalid format')
    return normalized
