from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ada_command_center.domain.alarms.configuration import AlarmConfiguration
from ada_command_center.domain.alarms.errors import AlarmConfigurationValidationError


@dataclass(frozen=True, slots=True)
class AlarmConfigurationSnapshot:
    configuration: AlarmConfiguration
    confirmed_tool_catalog_revision: str

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, AlarmConfiguration):
            raise TypeError('configuration must be an AlarmConfiguration')
        revision = _require_clean_text(
            self.confirmed_tool_catalog_revision,
            'confirmed_tool_catalog_revision',
        )
        object.__setattr__(self, 'confirmed_tool_catalog_revision', revision)

    def to_document(self) -> dict[str, object]:
        return {
            'configuration': self.configuration.to_document(),
            'confirmed_tool_catalog_revision': self.confirmed_tool_catalog_revision,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> AlarmConfigurationSnapshot:
        try:
            configuration = document['configuration']
            if not isinstance(configuration, Mapping):
                raise TypeError
            return cls(
                configuration=AlarmConfiguration.from_document(configuration),
                confirmed_tool_catalog_revision=_require_clean_text(
                    document['confirmed_tool_catalog_revision'],
                    'confirmed_tool_catalog_revision',
                ),
            )
        except AlarmConfigurationValidationError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise AlarmConfigurationValidationError(
                'Alarm Configuration snapshot document contract is invalid'
            ) from error


def _require_clean_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f'{field_name} must be text')
    normalized = value.strip()
    if not normalized or normalized != value:
        raise ValueError(f'{field_name} has an invalid format')
    return normalized
