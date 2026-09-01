from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ada.configuration.tools import ToolConfiguration, ToolConfigurationValidationError

TOOL_CONFIGURATION_SOURCE_SNAPSHOT_DOCUMENT_TYPE = 'ada_tool_configuration_source_snapshot'
TOOL_CONFIGURATION_SOURCE_SNAPSHOT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ToolConfigurationSourceSnapshot:
    configuration: ToolConfiguration
    revision: str
    saved_by: str
    saved_at_utc: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, ToolConfiguration):
            raise ToolConfigurationValidationError(
                'Tool configuration source snapshot configuration is invalid'
            )
        expected_revision = build_tool_configuration_digest(self.configuration)
        if not isinstance(self.revision, str) or self.revision.strip() != expected_revision:
            raise ToolConfigurationValidationError(
                'Tool configuration source snapshot revision does not match content'
            )
        actor = self.saved_by.strip() if isinstance(self.saved_by, str) else ''
        if not actor:
            raise ToolConfigurationValidationError(
                'Tool configuration source snapshot audit actor must not be empty'
            )
        if self.saved_at_utc.tzinfo is None or self.saved_at_utc.utcoffset() is None:
            raise ToolConfigurationValidationError(
                'Tool configuration source snapshot timestamp must be timezone-aware'
            )
        object.__setattr__(self, 'revision', expected_revision)
        object.__setattr__(self, 'saved_by', actor)
        object.__setattr__(self, 'saved_at_utc', self.saved_at_utc.astimezone(UTC))

    @classmethod
    def create(
        cls,
        *,
        configuration: ToolConfiguration,
        saved_by: str,
        saved_at_utc: datetime | None = None,
    ) -> ToolConfigurationSourceSnapshot:
        return cls(
            configuration=configuration,
            revision=build_tool_configuration_digest(configuration),
            saved_by=saved_by,
            saved_at_utc=saved_at_utc if saved_at_utc is not None else datetime.now(UTC),
        )

    def to_document(self) -> dict[str, object]:
        return {
            'document_type': TOOL_CONFIGURATION_SOURCE_SNAPSHOT_DOCUMENT_TYPE,
            'schema_version': TOOL_CONFIGURATION_SOURCE_SNAPSHOT_SCHEMA_VERSION,
            'revision': self.revision,
            'saved_by': self.saved_by,
            'saved_at_utc': self.saved_at_utc.isoformat(),
            'configuration': self.configuration.to_document(),
        }

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, Any],
    ) -> ToolConfigurationSourceSnapshot:
        if document.get('document_type') != TOOL_CONFIGURATION_SOURCE_SNAPSHOT_DOCUMENT_TYPE:
            raise ToolConfigurationValidationError(
                'Tool configuration source snapshot document type is invalid'
            )
        if document.get('schema_version') != TOOL_CONFIGURATION_SOURCE_SNAPSHOT_SCHEMA_VERSION:
            raise ToolConfigurationValidationError(
                'Tool configuration source snapshot schema version is invalid'
            )
        try:
            configuration = document['configuration']
            if not isinstance(configuration, Mapping):
                raise TypeError
            return cls(
                configuration=ToolConfiguration.from_document(configuration),
                revision=document['revision'],
                saved_by=document['saved_by'],
                saved_at_utc=datetime.fromisoformat(str(document['saved_at_utc'])),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ToolConfigurationValidationError):
                raise
            raise ToolConfigurationValidationError(
                'Tool configuration source snapshot contract is invalid'
            ) from error


def build_tool_configuration_digest(configuration: ToolConfiguration) -> str:
    if not isinstance(configuration, ToolConfiguration):
        raise ToolConfigurationValidationError('Tool Configuration is invalid')
    canonical = json.dumps(
        configuration.to_document(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()
