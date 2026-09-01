from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ada.configuration.tools import ToolConfiguration, ToolConfigurationValidationError

TOOL_CONFIGURATION_PROJECTION_SNAPSHOT_DOCUMENT_TYPE = 'ada_tool_configuration_projection_snapshot'
TOOL_CONFIGURATION_PROJECTION_SNAPSHOT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ToolConfigurationProjectionSnapshot:
    configuration: ToolConfiguration
    revision: str
    source_revision: str
    projected_by: str
    projected_at_utc: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.configuration, ToolConfiguration):
            raise ToolConfigurationValidationError(
                'Tool configuration projection snapshot configuration is invalid'
            )
        source_revision = (
            self.source_revision.strip() if isinstance(self.source_revision, str) else ''
        )
        actor = self.projected_by.strip() if isinstance(self.projected_by, str) else ''
        if not source_revision or not actor:
            raise ToolConfigurationValidationError(
                'Tool configuration projection snapshot metadata must not be empty'
            )
        if self.projected_at_utc.tzinfo is None or self.projected_at_utc.utcoffset() is None:
            raise ToolConfigurationValidationError(
                'Tool configuration projection snapshot timestamp must be timezone-aware'
            )
        occurred_at = self.projected_at_utc.astimezone(UTC)
        expected_revision = build_tool_configuration_projection_revision(
            source_revision=source_revision,
            projected_by=actor,
            projected_at_utc=occurred_at,
        )
        if not isinstance(self.revision, str) or self.revision.strip() != expected_revision:
            raise ToolConfigurationValidationError(
                'Tool configuration projection snapshot revision does not match metadata'
            )
        object.__setattr__(self, 'revision', expected_revision)
        object.__setattr__(self, 'source_revision', source_revision)
        object.__setattr__(self, 'projected_by', actor)
        object.__setattr__(self, 'projected_at_utc', occurred_at)

    @classmethod
    def create(
        cls,
        *,
        configuration: ToolConfiguration,
        source_revision: str,
        projected_by: str,
        projected_at_utc: datetime,
    ) -> ToolConfigurationProjectionSnapshot:
        return cls(
            configuration=configuration,
            revision=build_tool_configuration_projection_revision(
                source_revision=source_revision,
                projected_by=projected_by,
                projected_at_utc=projected_at_utc,
            ),
            source_revision=source_revision,
            projected_by=projected_by,
            projected_at_utc=projected_at_utc,
        )

    def to_document(self) -> dict[str, object]:
        return {
            'document_type': TOOL_CONFIGURATION_PROJECTION_SNAPSHOT_DOCUMENT_TYPE,
            'schema_version': TOOL_CONFIGURATION_PROJECTION_SNAPSHOT_SCHEMA_VERSION,
            'revision': self.revision,
            'source_revision': self.source_revision,
            'projected_by': self.projected_by,
            'projected_at_utc': self.projected_at_utc.isoformat(),
            'configuration': self.configuration.to_document(),
        }

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, Any],
    ) -> ToolConfigurationProjectionSnapshot:
        if document.get('document_type') != TOOL_CONFIGURATION_PROJECTION_SNAPSHOT_DOCUMENT_TYPE:
            raise ToolConfigurationValidationError(
                'Tool configuration projection snapshot document type is invalid'
            )
        if document.get('schema_version') != TOOL_CONFIGURATION_PROJECTION_SNAPSHOT_SCHEMA_VERSION:
            raise ToolConfigurationValidationError(
                'Tool configuration projection snapshot schema version is invalid'
            )
        try:
            configuration = document['configuration']
            if not isinstance(configuration, Mapping):
                raise TypeError
            return cls(
                configuration=ToolConfiguration.from_document(configuration),
                revision=document['revision'],
                source_revision=document['source_revision'],
                projected_by=document['projected_by'],
                projected_at_utc=datetime.fromisoformat(str(document['projected_at_utc'])),
            )
        except (KeyError, TypeError, ValueError) as error:
            if isinstance(error, ToolConfigurationValidationError):
                raise
            raise ToolConfigurationValidationError(
                'Tool configuration projection snapshot contract is invalid'
            ) from error


def build_tool_configuration_projection_revision(
    *,
    source_revision: str,
    projected_by: str,
    projected_at_utc: datetime,
) -> str:
    normalized_source = source_revision.strip() if isinstance(source_revision, str) else ''
    normalized_actor = projected_by.strip() if isinstance(projected_by, str) else ''
    if not normalized_source or not normalized_actor:
        raise ToolConfigurationValidationError(
            'Tool configuration projection metadata must not be empty'
        )
    if projected_at_utc.tzinfo is None or projected_at_utc.utcoffset() is None:
        raise ToolConfigurationValidationError(
            'Tool configuration projection timestamp must be timezone-aware'
        )
    payload = ':'.join(
        (
            normalized_source,
            normalized_actor,
            projected_at_utc.astimezone(UTC).isoformat(),
        )
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()
