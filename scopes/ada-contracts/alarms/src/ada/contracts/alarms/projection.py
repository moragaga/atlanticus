from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any

from ada.contracts.alarms.errors import AlarmConfigurationProjectionValidationError
from ada.contracts.alarms.snapshot import AlarmConfigurationSnapshot

ALARM_CONFIGURATION_SOURCE_KEY = 'alarm-configuration'
ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE = (
    'ada_command_center_alarm_configuration_projection_record'
)
ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION = 1


def alarm_configuration_projection_item_id(source_key: str) -> str:
    _require_text(source_key, 'source_key')
    digest = sha256(source_key.encode('utf-8')).hexdigest()
    return f'ada-command-center-alarm-configuration-projection-{digest}'


@dataclass(frozen=True, slots=True)
class AlarmConfigurationProjectionDependency:
    source_key: str
    source_release_id: str
    source_published_at_utc: datetime
    dependencies: tuple[AlarmConfigurationProjectionDependency, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.source_key, 'source_key')
        _require_text(self.source_release_id, 'source_release_id')
        _require_aware_datetime(self.source_published_at_utc, 'source_published_at_utc')
        if not isinstance(self.dependencies, tuple):
            raise TypeError('dependencies must be a tuple')
        for dependency in self.dependencies:
            if not isinstance(dependency, AlarmConfigurationProjectionDependency):
                raise TypeError(
                    'dependencies must contain AlarmConfigurationProjectionDependency values'
                )

    def to_document(self) -> dict[str, object]:
        return {
            'source_key': self.source_key,
            'source_release_id': self.source_release_id,
            'source_published_at_utc': self.source_published_at_utc.isoformat(),
            'dependencies': [dependency.to_document() for dependency in self.dependencies],
        }

    @classmethod
    def from_document(
        cls,
        document: Mapping[str, Any],
    ) -> AlarmConfigurationProjectionDependency:
        try:
            dependencies = document['dependencies']
            if not isinstance(dependencies, list):
                raise TypeError
            if any(not isinstance(dependency, Mapping) for dependency in dependencies):
                raise TypeError
            return cls(
                source_key=_text(document, 'source_key'),
                source_release_id=_text(document, 'source_release_id'),
                source_published_at_utc=datetime.fromisoformat(
                    _text(document, 'source_published_at_utc')
                ),
                dependencies=tuple(cls.from_document(dependency) for dependency in dependencies),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise AlarmConfigurationProjectionValidationError(
                'Alarm Configuration projection dependency contract is invalid'
            ) from error


@dataclass(frozen=True, slots=True)
class AlarmConfigurationProjection:
    source_key: str
    source_release_id: str
    source_published_at_utc: datetime
    projected_at_utc: datetime
    snapshot: AlarmConfigurationSnapshot
    dependencies: tuple[AlarmConfigurationProjectionDependency, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.source_key, 'source_key')
        _require_text(self.source_release_id, 'source_release_id')
        _require_aware_datetime(self.source_published_at_utc, 'source_published_at_utc')
        _require_aware_datetime(self.projected_at_utc, 'projected_at_utc')
        if not isinstance(self.snapshot, AlarmConfigurationSnapshot):
            raise TypeError('snapshot must be an AlarmConfigurationSnapshot')
        if not isinstance(self.dependencies, tuple):
            raise TypeError('dependencies must be a tuple')
        for dependency in self.dependencies:
            if not isinstance(dependency, AlarmConfigurationProjectionDependency):
                raise TypeError(
                    'dependencies must contain AlarmConfigurationProjectionDependency values'
                )

    @property
    def confirmed_tool_catalog_revision(self) -> str:
        return self.snapshot.confirmed_tool_catalog_revision

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            self.to_document(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        return sha256(payload).hexdigest()

    def to_document(
        self,
        *,
        item_id: str | None = None,
        partition_key: str | None = None,
    ) -> dict[str, object]:
        document: dict[str, object] = {
            'document_type': ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE,
            'schema_version': ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION,
            'source_key': self.source_key,
            'source_release_id': self.source_release_id,
            'source_published_at_utc': self.source_published_at_utc.isoformat(),
            'projected_at_utc': self.projected_at_utc.isoformat(),
            'dependencies': [dependency.to_document() for dependency in self.dependencies],
            'payload': self.snapshot.to_document(),
        }
        if item_id is not None:
            document['id'] = item_id
        if partition_key is not None:
            document['partition_key'] = partition_key
        return document

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> AlarmConfigurationProjection:
        if not isinstance(document, Mapping):
            raise AlarmConfigurationProjectionValidationError(
                'Alarm Configuration projection must be an object'
            )
        if document.get('document_type') != ALARM_CONFIGURATION_PROJECTION_DOCUMENT_TYPE:
            raise AlarmConfigurationProjectionValidationError(
                'Alarm Configuration projection document type is invalid'
            )
        if document.get('schema_version') != ALARM_CONFIGURATION_PROJECTION_SCHEMA_VERSION:
            raise AlarmConfigurationProjectionValidationError(
                'Alarm Configuration projection schema version is invalid'
            )
        try:
            payload = document['payload']
            dependencies = document['dependencies']
            if not isinstance(payload, Mapping) or not isinstance(dependencies, list):
                raise TypeError
            if any(not isinstance(item, Mapping) for item in dependencies):
                raise TypeError
            return cls(
                source_key=_text(document, 'source_key'),
                source_release_id=_text(document, 'source_release_id'),
                source_published_at_utc=datetime.fromisoformat(
                    _text(document, 'source_published_at_utc')
                ),
                projected_at_utc=datetime.fromisoformat(_text(document, 'projected_at_utc')),
                snapshot=AlarmConfigurationSnapshot.from_document(payload),
                dependencies=tuple(
                    AlarmConfigurationProjectionDependency.from_document(dependency)
                    for dependency in dependencies
                ),
            )
        except AlarmConfigurationProjectionValidationError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            raise AlarmConfigurationProjectionValidationError(
                'Alarm Configuration projection contract is invalid'
            ) from error


def _text(document: Mapping[str, Any], field_name: str) -> str:
    value = document[field_name]
    if not isinstance(value, str):
        raise TypeError(f'{field_name} must be text')
    return value


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f'{name} must be text')
    if not value or value.strip() != value:
        raise ValueError(f'{name} must be non-empty text without surrounding whitespace')


def _require_aware_datetime(value: object, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f'{name} must be a datetime')
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f'{name} must be timezone-aware')
