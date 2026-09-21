# Serialización JSON estable del snapshot CURRENT.
# El codec conserva únicamente el read model necesario y valida document_type/schema_version.
# Al reconstruir el snapshot también se verifica que la revisión corresponda al contenido.

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from ada.web.tools.enums import ToolConfigurationKind
from ada.web.tools.structure import ToolStructure
from ada_command_center.tools.catalog.errors import (
    ToolCatalogCodecError,
    ToolCatalogValidationError,
)
from ada_command_center.tools.catalog.models import ToolCatalogEntry, ToolCatalogSnapshot
from atlanticus.web.source.models import SourceReleaseId

TOOL_CATALOG_DOCUMENT_TYPE = 'ada_command_center_tool_catalog'
TOOL_CATALOG_SCHEMA_VERSION = 1


def tool_catalog_to_bytes(snapshot: ToolCatalogSnapshot) -> bytes:
    if not isinstance(snapshot, ToolCatalogSnapshot):
        raise ToolCatalogCodecError('Tool Catalog snapshot is invalid')
    document = {
        'document_type': TOOL_CATALOG_DOCUMENT_TYPE,
        'schema_version': TOOL_CATALOG_SCHEMA_VERSION,
        'revision': snapshot.revision,
        'generated_at_utc': snapshot.generated_at_utc.isoformat(),
        'tools': [_entry_to_document(tool) for tool in snapshot.tools],
    }
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')


def tool_catalog_from_bytes(payload: bytes) -> ToolCatalogSnapshot:
    if not isinstance(payload, bytes):
        raise ToolCatalogCodecError('Tool Catalog payload must be bytes')
    try:
        document = json.loads(payload.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolCatalogCodecError('Tool Catalog payload is not valid JSON') from error
    if not isinstance(document, Mapping):
        raise ToolCatalogCodecError('Tool Catalog payload root must be an object')
    if document.get('document_type') != TOOL_CATALOG_DOCUMENT_TYPE:
        raise ToolCatalogCodecError('Tool Catalog document type is invalid')
    if document.get('schema_version') != TOOL_CATALOG_SCHEMA_VERSION:
        raise ToolCatalogCodecError('Tool Catalog schema version is invalid')
    try:
        tools = _require_list(document['tools'])
        return ToolCatalogSnapshot(
            revision=_require_string(document['revision']),
            generated_at_utc=datetime.fromisoformat(_require_string(document['generated_at_utc'])),
            tools=tuple(_entry_from_document(item) for item in tools),
        )
    except (KeyError, TypeError, ValueError, ToolCatalogValidationError) as error:
        raise ToolCatalogCodecError('Tool Catalog document contract is invalid') from error


def _entry_to_document(entry: ToolCatalogEntry) -> dict[str, object]:
    return {
        'tool_key': entry.tool_key,
        'display_name': entry.display_name,
        'kind': entry.kind.value,
        'source_release_id': entry.source_release_id.value,
        'structure': entry.structure.to_document(),
    }


def _entry_from_document(document: object) -> ToolCatalogEntry:
    value = _require_mapping(document)
    structure = _require_mapping(value['structure'])
    return ToolCatalogEntry(
        tool_key=_require_string(value['tool_key']),
        display_name=_require_string(value['display_name']),
        kind=ToolConfigurationKind(_require_string(value['kind'])),
        source_release_id=SourceReleaseId(_require_string(value['source_release_id'])),
        structure=ToolStructure.from_document(structure),
    )


def _require_mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError
    return value


def _require_list(value: object) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError
    return value


def _require_string(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value
