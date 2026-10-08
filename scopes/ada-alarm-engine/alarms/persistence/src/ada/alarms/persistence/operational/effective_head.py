from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ada.alarms.persistence.operational.configuration_adoption import (
    AlarmArtifactRefSnapshot,
    ConfigurationAdoptionRecord,
)
from ada.alarms.persistence.operational.errors import AlarmPersistenceCorruptionError
from ada.alarms.persistence.operational.models import JournalEntry, JournalPosition
from atlanticus.json import JsonDocument

ALARM_EFFECTIVE_HEAD_SCHEMA_VERSION = 'alarm-effective-head.v1'
_HASH_PATTERN = re.compile(r'sha256:[0-9a-f]{64}')


@dataclass(frozen=True, slots=True)
class AlarmEffectiveConfigurationHead:
    adoption_id: str
    adoption_record_hash: str
    adoption_position: JournalPosition
    target_artifact_ref: AlarmArtifactRefSnapshot
    effective_at: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.adoption_id, str)
            or not self.adoption_id
            or self.adoption_id.strip() != self.adoption_id
        ):
            raise ValueError('adoption_id must be non-empty text without surrounding whitespace')
        if (
            not isinstance(self.adoption_record_hash, str)
            or _HASH_PATTERN.fullmatch(self.adoption_record_hash) is None
        ):
            raise ValueError('adoption_record_hash must be a canonical SHA-256 digest')
        if not isinstance(self.adoption_position, JournalPosition):
            raise TypeError('adoption_position must be a JournalPosition')
        if self.adoption_position.commit_id != self.adoption_id:
            raise ValueError('adoption_position must identify adoption_id')
        if not isinstance(self.target_artifact_ref, AlarmArtifactRefSnapshot):
            raise TypeError('target_artifact_ref must be an AlarmArtifactRefSnapshot')
        if not isinstance(self.effective_at, str):
            raise TypeError('effective_at must be an ISO-8601 UTC string')
        try:
            timestamp = datetime.fromisoformat(self.effective_at.replace('Z', '+00:00'))
        except ValueError as error:
            raise ValueError('effective_at must be an ISO-8601 UTC string') from error
        if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
            raise ValueError('effective_at must be timezone-aware UTC')

    @classmethod
    def from_adoption_entry(cls, entry: JournalEntry) -> AlarmEffectiveConfigurationHead:
        if not isinstance(entry, JournalEntry) or not isinstance(
            entry.record, ConfigurationAdoptionRecord
        ):
            raise TypeError('entry must contain a configuration adoption record')
        record = entry.record
        return cls(
            adoption_id=record.adoption_id,
            adoption_record_hash=record.record_hash,
            adoption_position=entry.end,
            target_artifact_ref=record.target_artifact_ref,
            effective_at=record.effective_at,
        )

    def as_document(self) -> JsonDocument:
        return {
            'schema_version': ALARM_EFFECTIVE_HEAD_SCHEMA_VERSION,
            'adoption_id': self.adoption_id,
            'adoption_record_hash': self.adoption_record_hash,
            'adoption_position': self.adoption_position.as_document(),
            'target_artifact_ref': self.target_artifact_ref.as_document(),
            'effective_at': self.effective_at,
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> AlarmEffectiveConfigurationHead:
        required = {
            'schema_version',
            'adoption_id',
            'adoption_record_hash',
            'adoption_position',
            'target_artifact_ref',
            'effective_at',
        }
        if not isinstance(value, Mapping) or set(value) != required:
            raise AlarmPersistenceCorruptionError('effective head has invalid fields')
        if value['schema_version'] != ALARM_EFFECTIVE_HEAD_SCHEMA_VERSION:
            raise AlarmPersistenceCorruptionError('effective head schema version is unsupported')
        try:
            return cls(
                adoption_id=value['adoption_id'],
                adoption_record_hash=value['adoption_record_hash'],
                adoption_position=JournalPosition.from_document(value['adoption_position']),
                target_artifact_ref=AlarmArtifactRefSnapshot.from_document(
                    value['target_artifact_ref']
                ),
                effective_at=value['effective_at'],
            )
        except (TypeError, ValueError) as error:
            raise AlarmPersistenceCorruptionError('effective head is invalid') from error
