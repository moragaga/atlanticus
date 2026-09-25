from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ada_command_center.domain.alarms.configuration import AlarmConfiguration
from ada_command_center.domain.alarms.errors import AlarmConfigurationValidationError
from ada_command_center.domain.tools import ToolDependencyManifest


# Congela una configuración junto al subconjunto exacto de Tools que respaldó su publicación.
# La revisión del catálogo se deriva del manifest para evitar dos identidades duplicadas.
@dataclass(frozen=True, slots=True)
class AlarmConfigurationSnapshot:
    configuration: AlarmConfiguration
    tool_dependencies: ToolDependencyManifest

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, AlarmConfiguration):
            raise TypeError('configuration must be an AlarmConfiguration')
        if not isinstance(self.tool_dependencies, ToolDependencyManifest):
            raise TypeError('tool_dependencies must be a ToolDependencyManifest')

    # Compatibilidad semántica para consumidores: la identidad Tools vive en el manifest.
    @property
    def confirmed_tool_catalog_revision(self) -> str:
        return self.tool_dependencies.revision

    # El documento durable contiene configuración authored y evidencia Tools autocontenida.
    def to_document(self) -> dict[str, object]:
        return {
            'configuration': self.configuration.to_document(),
            'tool_dependencies': self.tool_dependencies.to_document(),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> AlarmConfigurationSnapshot:
        try:
            configuration = document['configuration']
            tool_dependencies = document['tool_dependencies']
            if not isinstance(configuration, Mapping):
                raise TypeError
            if not isinstance(tool_dependencies, Mapping):
                raise TypeError
            return cls(
                configuration=AlarmConfiguration.from_document(configuration),
                tool_dependencies=ToolDependencyManifest.from_document(tool_dependencies),
            )
        except AlarmConfigurationValidationError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise AlarmConfigurationValidationError(
                'Alarm Configuration snapshot document contract is invalid'
            ) from error
