from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ada_command_center.domain.alarms.configuration import AlarmConfiguration
from ada_command_center.domain.alarms.errors import AlarmConfigurationValidationError


# Representa una configuración de alarmas ya confirmada contra una revisión concreta
# del catálogo de Tools. La configuración sigue siendo el contenido authored puro;
# este snapshot agrega únicamente la genealogía transversal necesaria para publicación,
# proyección y posterior materialización.
@dataclass(frozen=True, slots=True)
class AlarmConfigurationSnapshot:
    configuration: AlarmConfiguration
    confirmed_tool_catalog_revision: str

    def __post_init__(self) -> None:
        # El snapshot nunca acepta payloads parcialmente tipados: debe envolver exactamente
        # el contrato transversal AlarmConfiguration.
        if not isinstance(self.configuration, AlarmConfiguration):
            raise TypeError('configuration must be an AlarmConfiguration')
        revision = _require_clean_text(
            self.confirmed_tool_catalog_revision,
            'confirmed_tool_catalog_revision',
        )
        object.__setattr__(self, 'confirmed_tool_catalog_revision', revision)

    def to_document(self) -> dict[str, object]:
        # La revisión Tools viaja junto al contenido sin modificar el shape interno de
        # AlarmConfiguration. Así un draft puede seguir siendo sólo rules/messages.
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
    # Las revisiones son identidades; no se normalizan silenciosamente porque eso podría
    # ocultar una correlación distinta a la que fue publicada.
    if not isinstance(value, str):
        raise TypeError(f'{field_name} must be text')
    normalized = value.strip()
    if not normalized or normalized != value:
        raise ValueError(f'{field_name} has an invalid format')
    return normalized
