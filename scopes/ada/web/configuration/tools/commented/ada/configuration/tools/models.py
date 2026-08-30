from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ada.configuration.tool_source_consumption import ToolSourceConsumption
from ada.configuration.tool_source_operational_participation import (
    ToolSourceOperationalParticipation,
    validate_operational_participation_against_consumption,
)
from ada.configuration.tools.errors import ToolConfigurationValidationError

# Las identidades de Tool mantienen el mismo formato canónico usado por los contratos de Sources.
_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


class ToolConfigurationKind(StrEnum):
    # Los tipos actuales describen las dos composiciones operacionales ADA existentes.
    INTEGRATED_OPERATIONS = 'integrated_operations'
    PROCESS = 'process'


@dataclass(frozen=True, slots=True)
class ToolConfiguration:
    # La Tool conserva su identidad funcional y reutiliza directamente los contratos DATA-003/004.
    tool_key: str
    display_name: str
    kind: ToolConfigurationKind
    source_consumption: ToolSourceConsumption
    source_operational_participation: ToolSourceOperationalParticipation

    def __post_init__(self) -> None:
        # Primero normalizamos la identidad propia antes de cruzarla con los contratos anidados.
        tool_key = _require_key(self.tool_key, label='Tool key')
        display_name = _require_display_name(self.display_name)
        if not isinstance(self.kind, ToolConfigurationKind):
            raise ToolConfigurationValidationError('Tool kind is invalid')
        # Tool Configuration no redefine DATA-003 ni DATA-004: exige sus contratos reales.
        if not isinstance(self.source_consumption, ToolSourceConsumption):
            raise ToolConfigurationValidationError('Tool source consumption contract is invalid')
        if not isinstance(
            self.source_operational_participation,
            ToolSourceOperationalParticipation,
        ):
            raise ToolConfigurationValidationError(
                'Tool source operational participation contract is invalid'
            )
        # Las tres identidades deben apuntar a la misma Tool para evitar configuraciones cruzadas.
        if self.source_consumption.tool_key != tool_key:
            raise ToolConfigurationValidationError(
                'Tool source consumption tool key must match Tool Configuration tool key'
            )
        if self.source_operational_participation.tool_key != tool_key:
            raise ToolConfigurationValidationError(
                'Tool source operational participation tool key must match '
                'Tool Configuration tool key'
            )
        # DATA-004 solo puede clasificar fuentes previamente declaradas por DATA-003.
        try:
            validate_operational_participation_against_consumption(
                consumption=self.source_consumption,
                participation=self.source_operational_participation,
            )
        except ValueError as error:
            raise ToolConfigurationValidationError(str(error)) from error
        object.__setattr__(self, 'tool_key', tool_key)
        object.__setattr__(self, 'display_name', display_name)

    def to_document(self) -> dict[str, object]:
        # La persistencia conserva los dos contratos completos para que Manager y runtime compartan forma.
        return {
            'tool_key': self.tool_key,
            'display_name': self.display_name,
            'kind': self.kind.value,
            'source_consumption': self.source_consumption.to_document(),
            'source_operational_participation': (
                self.source_operational_participation.to_document()
            ),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> ToolConfiguration:
        # La restauración delega cada subdocumento al contrato que realmente es dueño de su semántica.
        try:
            source_consumption = document['source_consumption']
            source_operational_participation = document['source_operational_participation']
            if not isinstance(source_consumption, Mapping):
                raise TypeError
            if not isinstance(source_operational_participation, Mapping):
                raise TypeError
            return cls(
                tool_key=document['tool_key'],
                display_name=document['display_name'],
                kind=ToolConfigurationKind(document['kind']),
                source_consumption=ToolSourceConsumption.from_document(source_consumption),
                source_operational_participation=(
                    ToolSourceOperationalParticipation.from_document(
                        source_operational_participation
                    )
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ToolConfigurationValidationError):
                raise
            raise ToolConfigurationValidationError(
                'Tool Configuration contract is invalid'
            ) from error


def _require_key(value: object, *, label: str) -> str:
    # Las identidades se normalizan en minúsculas y se rechazan si no son canónicas.
    if not isinstance(value, str):
        raise ToolConfigurationValidationError(f'{label} must be a string')
    normalized = value.strip().casefold()
    if not _KEY_PATTERN.fullmatch(normalized):
        raise ToolConfigurationValidationError(f'{label} has an invalid format')
    return normalized


def _require_display_name(value: object) -> str:
    # El nombre visible puede contener espacios, pero debe contener texto real.
    if not isinstance(value, str):
        raise ToolConfigurationValidationError('Tool display name must be a string')
    normalized = value.strip()
    if not normalized:
        raise ToolConfigurationValidationError('Tool display name must not be empty')
    return normalized
