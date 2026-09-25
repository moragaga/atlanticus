from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ada.web.tools.enums import ToolConfigurationKind
from ada.web.tools.errors import ToolConfigurationValidationError
from ada.web.tools.structure import ToolStructure
from ada_command_center.domain.tools.errors import ToolDependencyManifestValidationError


# Congela la identidad y estructura de una Tool exactamente como fue usada por un consumidor.
# display_name y ToolStructure preservan nombres históricos sin obligar a consultar
# contratos futuros.
@dataclass(frozen=True, slots=True)
class ToolDependencyEntry:
    tool_key: str
    display_name: str
    source_release_id: str
    kind: ToolConfigurationKind
    structure: ToolStructure

    def __post_init__(self) -> None:
        tool_key = _require_clean_text(self.tool_key, 'tool_key')
        display_name = _require_clean_text(self.display_name, 'display_name')
        source_release_id = _require_clean_text(self.source_release_id, 'source_release_id')
        if not isinstance(self.kind, ToolConfigurationKind):
            raise ToolDependencyManifestValidationError('Tool dependency kind is invalid')
        if not isinstance(self.structure, ToolStructure):
            raise ToolDependencyManifestValidationError('Tool dependency structure is invalid')
        # La entrada y su estructura deben representar la misma Tool y el mismo tipo.
        if self.structure.tool_key != tool_key:
            raise ToolDependencyManifestValidationError(
                'Tool dependency structure tool key does not match entry'
            )
        if self.structure.kind is not self.kind:
            raise ToolDependencyManifestValidationError(
                'Tool dependency structure kind does not match entry'
            )
        object.__setattr__(self, 'tool_key', tool_key)
        object.__setattr__(self, 'display_name', display_name)
        object.__setattr__(self, 'source_release_id', source_release_id)

    def to_document(self) -> dict[str, object]:
        # El documento conserva la estructura completa para historia y resolución posterior.
        return {
            'tool_key': self.tool_key,
            'display_name': self.display_name,
            'source_release_id': self.source_release_id,
            'kind': self.kind.value,
            'structure': self.structure.to_document(),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> ToolDependencyEntry:
        try:
            raw_structure = document['structure']
            if not isinstance(raw_structure, Mapping):
                raise TypeError
            return cls(
                tool_key=document['tool_key'],
                display_name=document['display_name'],
                source_release_id=document['source_release_id'],
                kind=ToolConfigurationKind(document['kind']),
                structure=ToolStructure.from_document(raw_structure),
            )
        except ToolDependencyManifestValidationError:
            raise
        except (KeyError, TypeError, ValueError, ToolConfigurationValidationError) as error:
            raise ToolDependencyManifestValidationError(
                'Tool dependency entry contract is invalid'
            ) from error


# Representa el subconjunto congelado de Tools que respaldó una configuración concreta.
# La revisión pertenece al catálogo confirmado completo; no se recalcula desde este subconjunto.
@dataclass(frozen=True, slots=True)
class ToolDependencyManifest:
    confirmed_tool_catalog_revision: str
    tools: tuple[ToolDependencyEntry, ...]

    def __post_init__(self) -> None:
        revision = _require_clean_text(
            self.confirmed_tool_catalog_revision,
            'confirmed_tool_catalog_revision',
        )
        tools = tuple(self.tools)
        if any(not isinstance(tool, ToolDependencyEntry) for tool in tools):
            raise ToolDependencyManifestValidationError(
                'Tool dependency manifest tools must contain ToolDependencyEntry values'
            )
        # El orden canónico vuelve estable la serialización y evita diferencias por inserción.
        ordered = tuple(sorted(tools, key=lambda tool: tool.tool_key))
        keys = tuple(tool.tool_key for tool in ordered)
        if len(keys) != len(set(keys)):
            raise ToolDependencyManifestValidationError(
                'Tool dependency manifest tool_key values must be unique'
            )
        object.__setattr__(self, 'confirmed_tool_catalog_revision', revision)
        object.__setattr__(self, 'tools', ordered)

    @property
    def revision(self) -> str:
        # B.2 ya consume estructuralmente un catálogo que expone revision + get(tool_key).
        return self.confirmed_tool_catalog_revision

    def get(self, tool_key: str) -> ToolDependencyEntry | None:
        normalized = _require_clean_text(tool_key, 'tool_key')
        for tool in self.tools:
            if tool.tool_key == normalized:
                return tool
        return None

    def to_document(self) -> dict[str, object]:
        return {
            'confirmed_tool_catalog_revision': self.confirmed_tool_catalog_revision,
            'tools': [tool.to_document() for tool in self.tools],
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> ToolDependencyManifest:
        try:
            raw_tools = document['tools']
            if not isinstance(raw_tools, list):
                raise TypeError
            if not all(isinstance(item, Mapping) for item in raw_tools):
                raise TypeError
            return cls(
                confirmed_tool_catalog_revision=document['confirmed_tool_catalog_revision'],
                tools=tuple(ToolDependencyEntry.from_document(item) for item in raw_tools),
            )
        except ToolDependencyManifestValidationError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise ToolDependencyManifestValidationError(
                'Tool dependency manifest contract is invalid'
            ) from error


def _require_clean_text(value: object, field_name: str) -> str:
    # Las identidades se validan, no se corrigen silenciosamente.
    if not isinstance(value, str):
        raise ToolDependencyManifestValidationError(f'{field_name} must be text')
    normalized = value.strip()
    if not normalized or normalized != value:
        raise ToolDependencyManifestValidationError(f'{field_name} has an invalid format')
    return normalized
