from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ada.configuration.tool_sources import (
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
    validate_operational_participation_against_consumption,
)
from ada.configuration.tools.enums import ToolConfigurationKind
from ada.configuration.tools.errors import ToolConfigurationValidationError
from ada.configuration.tools.structure import ToolStructure
from ada.configuration.tools.validation import require_display_name, require_key


@dataclass(frozen=True, slots=True)
class ToolConfiguration:
    tool_key: str
    display_name: str
    kind: ToolConfigurationKind
    source_consumption: ToolSourceConsumption
    source_operational_participation: ToolSourceOperationalParticipation
    structure: ToolStructure | None = None

    def __post_init__(self) -> None:
        tool_key = require_key(self.tool_key, label='Tool key')
        display_name = require_display_name(
            self.display_name,
            label='Tool display name',
        )
        if not isinstance(self.kind, ToolConfigurationKind):
            raise ToolConfigurationValidationError('Tool kind is invalid')
        if not isinstance(self.source_consumption, ToolSourceConsumption):
            raise ToolConfigurationValidationError('Tool source consumption contract is invalid')
        if not isinstance(
            self.source_operational_participation,
            ToolSourceOperationalParticipation,
        ):
            raise ToolConfigurationValidationError(
                'Tool source operational participation contract is invalid'
            )
        if self.source_consumption.tool_key != tool_key:
            raise ToolConfigurationValidationError(
                'Tool source consumption tool key must match Tool Configuration tool key'
            )
        if self.source_operational_participation.tool_key != tool_key:
            raise ToolConfigurationValidationError(
                'Tool source operational participation tool key must match '
                'Tool Configuration tool key'
            )
        if self.structure is not None:
            if not isinstance(self.structure, ToolStructure):
                raise ToolConfigurationValidationError('Tool Structure contract is invalid')
            if self.structure.tool_key != tool_key:
                raise ToolConfigurationValidationError(
                    'Tool Structure tool key must match Tool Configuration tool key'
                )
            if self.structure.kind is not self.kind:
                raise ToolConfigurationValidationError(
                    'Tool Structure kind must match Tool Configuration kind'
                )
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
        return {
            'tool_key': self.tool_key,
            'display_name': self.display_name,
            'kind': self.kind.value,
            'source_consumption': self.source_consumption.to_document(),
            'source_operational_participation': (
                self.source_operational_participation.to_document()
            ),
            'structure': self.structure.to_document() if self.structure is not None else None,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> ToolConfiguration:
        try:
            source_consumption = document['source_consumption']
            source_operational_participation = document['source_operational_participation']
            raw_structure = document.get('structure')
            if not isinstance(source_consumption, Mapping):
                raise TypeError
            if not isinstance(source_operational_participation, Mapping):
                raise TypeError
            if raw_structure is not None and not isinstance(raw_structure, Mapping):
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
                structure=(
                    ToolStructure.from_document(raw_structure)
                    if raw_structure is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ToolConfigurationValidationError):
                raise
            raise ToolConfigurationValidationError(
                'Tool Configuration contract is invalid'
            ) from error
