from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from ada.web.tools.enums import ToolConfigurationKind
from ada.web.tools.structure import ToolStructure
from ada_command_center.tools.catalog.errors import ToolCatalogValidationError
from atlanticus.web.source.models import SourceReleaseId


@dataclass(frozen=True, slots=True)
class ToolCatalogEntry:
    tool_key: str
    display_name: str
    kind: ToolConfigurationKind
    source_release_id: SourceReleaseId
    structure: ToolStructure

    def __post_init__(self) -> None:
        tool_key = _require_text(self.tool_key, 'tool_key')
        display_name = _require_text(self.display_name, 'display_name')
        if not isinstance(self.kind, ToolConfigurationKind):
            raise ToolCatalogValidationError('Tool Catalog kind is invalid')
        if not isinstance(self.source_release_id, SourceReleaseId):
            raise ToolCatalogValidationError('Tool Catalog source release id is invalid')
        if not isinstance(self.structure, ToolStructure):
            raise ToolCatalogValidationError('Tool Catalog structure is invalid')
        if self.structure.tool_key != tool_key:
            raise ToolCatalogValidationError('Tool Catalog structure tool key does not match entry')
        if self.structure.kind is not self.kind:
            raise ToolCatalogValidationError('Tool Catalog structure kind does not match entry')
        object.__setattr__(self, 'tool_key', tool_key)
        object.__setattr__(self, 'display_name', display_name)


@dataclass(frozen=True, slots=True)
class ToolCatalogSnapshot:
    revision: str
    generated_at_utc: datetime
    tools: tuple[ToolCatalogEntry, ...]

    def __post_init__(self) -> None:
        revision = _require_text(self.revision, 'revision')
        generated_at_utc = _normalize_utc(self.generated_at_utc)
        tools = tuple(self.tools)
        if any(not isinstance(tool, ToolCatalogEntry) for tool in tools):
            raise ToolCatalogValidationError(
                'Tool Catalog tools must contain ToolCatalogEntry values'
            )
        ordered = tuple(sorted(tools, key=lambda tool: tool.tool_key))
        keys = tuple(tool.tool_key for tool in ordered)
        if len(keys) != len(set(keys)):
            raise ToolCatalogValidationError('Tool Catalog tool_key values must be unique')
        expected_revision = calculate_tool_catalog_revision(ordered)
        if revision != expected_revision:
            raise ToolCatalogValidationError('Tool Catalog revision does not match payload')
        object.__setattr__(self, 'revision', revision)
        object.__setattr__(self, 'generated_at_utc', generated_at_utc)
        object.__setattr__(self, 'tools', ordered)

    def get(self, tool_key: str) -> ToolCatalogEntry | None:
        normalized = _require_text(tool_key, 'tool_key')
        for tool in self.tools:
            if tool.tool_key == normalized:
                return tool
        return None


def create_tool_catalog_snapshot(
    tools: tuple[ToolCatalogEntry, ...],
    *,
    generated_at_utc: datetime,
) -> ToolCatalogSnapshot:
    ordered = tuple(sorted(tools, key=lambda tool: tool.tool_key))
    return ToolCatalogSnapshot(
        revision=calculate_tool_catalog_revision(ordered),
        generated_at_utc=generated_at_utc,
        tools=ordered,
    )


def calculate_tool_catalog_revision(tools: tuple[ToolCatalogEntry, ...]) -> str:
    document = [
        _entry_revision_document(tool) for tool in sorted(tools, key=lambda item: item.tool_key)
    ]
    payload = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def _entry_revision_document(entry: ToolCatalogEntry) -> dict[str, object]:
    return {
        'tool_key': entry.tool_key,
        'display_name': entry.display_name,
        'kind': entry.kind.value,
        'source_release_id': entry.source_release_id.value,
        'structure': entry.structure.to_document(),
    }


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ToolCatalogValidationError(f'{field_name} must be text')
    normalized = value.strip()
    if not normalized or normalized != value:
        raise ToolCatalogValidationError(f'{field_name} has an invalid format')
    return normalized


def _normalize_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise ToolCatalogValidationError('generated_at_utc must be a datetime')
    if value.tzinfo is None or value.utcoffset() is None:
        raise ToolCatalogValidationError('generated_at_utc must be timezone-aware')
    return value.astimezone(timezone.utc)
