from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ada.alarms.persistence.operational.errors import AlarmPersistenceCorruptionError
from ada.alarms.persistence.operational.serialization import build_record_hash
from atlanticus.json import JsonDocument

CONFIGURATION_ADOPTION_RECORD_SCHEMA_VERSION = 'configuration-adoption-record.v1'
CONFIGURATION_ADOPTION_RECORD_V2_SCHEMA_VERSION = 'configuration-adoption-record.v2'
_RESULT_PATTERN = re.compile(r'alarm-materialization-[0-9a-f]{64}')
_SHA256_PATTERN = re.compile(r'[0-9a-f]{64}')
_RECORD_HASH_PATTERN = re.compile(r'sha256:[0-9a-f]{64}')


@dataclass(frozen=True, slots=True)
class AlarmArtifactRefSnapshot:
    source_key: str
    result_id: str
    manifest_sha256: str
    alarm_configuration_revision: str
    confirmed_tool_catalog_revision: str

    def __post_init__(self) -> None:
        _require_text(self.source_key, 'source_key')
        if _RESULT_PATTERN.fullmatch(self.result_id) is None:
            raise ValueError('result_id must identify one materialization result')
        if _SHA256_PATTERN.fullmatch(self.manifest_sha256) is None:
            raise ValueError('manifest_sha256 must be a lowercase SHA-256 digest')
        _require_text(self.alarm_configuration_revision, 'alarm_configuration_revision')
        _require_text(self.confirmed_tool_catalog_revision, 'confirmed_tool_catalog_revision')

    def as_document(self) -> JsonDocument:
        return {
            'source_key': self.source_key,
            'result_id': self.result_id,
            'manifest_sha256': self.manifest_sha256,
            'resolution_key': {
                'alarm_configuration_revision': self.alarm_configuration_revision,
                'confirmed_tool_catalog_revision': self.confirmed_tool_catalog_revision,
            },
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> AlarmArtifactRefSnapshot:
        document = _require_exact_mapping(
            value,
            {'source_key', 'result_id', 'manifest_sha256', 'resolution_key'},
            'artifact reference',
        )
        resolution = _require_exact_mapping(
            document['resolution_key'],
            {'alarm_configuration_revision', 'confirmed_tool_catalog_revision'},
            'resolution key',
        )
        try:
            return cls(
                source_key=document['source_key'],
                result_id=document['result_id'],
                manifest_sha256=document['manifest_sha256'],
                alarm_configuration_revision=resolution['alarm_configuration_revision'],
                confirmed_tool_catalog_revision=resolution['confirmed_tool_catalog_revision'],
            )
        except (TypeError, ValueError) as error:
            raise AlarmPersistenceCorruptionError('artifact reference is invalid') from error


@dataclass(frozen=True, slots=True)
class ConfigurationAdoptionRecord:
    adoption_id: str
    previous_artifact_ref: AlarmArtifactRefSnapshot | None
    target_artifact_ref: AlarmArtifactRefSnapshot
    effective_at: str
    committed_at: str
    record_hash: str

    def __post_init__(self) -> None:
        _require_text(self.adoption_id, 'adoption_id')
        if self.previous_artifact_ref is not None and not isinstance(
            self.previous_artifact_ref, AlarmArtifactRefSnapshot
        ):
            raise TypeError('previous_artifact_ref must be AlarmArtifactRefSnapshot or None')
        if not isinstance(self.target_artifact_ref, AlarmArtifactRefSnapshot):
            raise TypeError('target_artifact_ref must be AlarmArtifactRefSnapshot')
        previous = self.previous_artifact_ref
        target = self.target_artifact_ref
        if previous is not None:
            if previous.source_key != target.source_key:
                raise ValueError('adoption artifact source_key must remain unchanged')
            if previous.result_id == target.result_id:
                raise ValueError('adoption source and target result_id must differ')
        effective = _require_utc_timestamp(self.effective_at, 'effective_at')
        committed = _require_utc_timestamp(self.committed_at, 'committed_at')
        if committed < effective:
            raise ValueError('committed_at must not be before effective_at')
        if (
            not isinstance(self.record_hash, str)
            or _RECORD_HASH_PATTERN.fullmatch(self.record_hash) is None
        ):
            raise ValueError('record_hash must be a canonical SHA-256 digest')

    @classmethod
    def create(
        cls,
        *,
        adoption_id: str,
        previous_artifact_ref: AlarmArtifactRefSnapshot | None,
        target_artifact_ref: AlarmArtifactRefSnapshot,
        effective_at: str,
        committed_at: str,
    ) -> ConfigurationAdoptionRecord:
        unsigned = _unsigned_document(
            adoption_id=adoption_id,
            previous_artifact_ref=previous_artifact_ref,
            target_artifact_ref=target_artifact_ref,
            effective_at=effective_at,
            committed_at=committed_at,
        )
        return cls(
            adoption_id=adoption_id,
            previous_artifact_ref=previous_artifact_ref,
            target_artifact_ref=target_artifact_ref,
            effective_at=effective_at,
            committed_at=committed_at,
            record_hash=build_record_hash(unsigned),
        )

    def unsigned_document(self) -> JsonDocument:
        return _unsigned_document(
            adoption_id=self.adoption_id,
            previous_artifact_ref=self.previous_artifact_ref,
            target_artifact_ref=self.target_artifact_ref,
            effective_at=self.effective_at,
            committed_at=self.committed_at,
        )

    def as_document(self) -> JsonDocument:
        return {**self.unsigned_document(), 'record_hash': self.record_hash}

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> ConfigurationAdoptionRecord:
        document = _require_exact_mapping(
            value,
            {
                'record_schema_version',
                'adoption_id',
                'previous_artifact_ref',
                'target_artifact_ref',
                'effective_at',
                'committed_at',
                'record_hash',
            },
            'configuration adoption record',
        )
        if document['record_schema_version'] != CONFIGURATION_ADOPTION_RECORD_SCHEMA_VERSION:
            raise AlarmPersistenceCorruptionError(
                'configuration adoption record schema version is unsupported'
            )
        previous = document['previous_artifact_ref']
        try:
            record = cls(
                adoption_id=document['adoption_id'],
                previous_artifact_ref=(
                    None if previous is None else AlarmArtifactRefSnapshot.from_document(previous)
                ),
                target_artifact_ref=AlarmArtifactRefSnapshot.from_document(
                    document['target_artifact_ref']
                ),
                effective_at=document['effective_at'],
                committed_at=document['committed_at'],
                record_hash=document['record_hash'],
            )
        except (TypeError, ValueError) as error:
            raise AlarmPersistenceCorruptionError(
                'configuration adoption record is invalid'
            ) from error
        if build_record_hash(record.unsigned_document()) != record.record_hash:
            raise AlarmPersistenceCorruptionError('configuration adoption record hash mismatch')
        return record


def _unsigned_document(
    *,
    adoption_id: str,
    previous_artifact_ref: AlarmArtifactRefSnapshot | None,
    target_artifact_ref: AlarmArtifactRefSnapshot,
    effective_at: str,
    committed_at: str,
) -> JsonDocument:
    if previous_artifact_ref is not None and not isinstance(
        previous_artifact_ref, AlarmArtifactRefSnapshot
    ):
        raise TypeError('previous_artifact_ref must be AlarmArtifactRefSnapshot or None')
    if not isinstance(target_artifact_ref, AlarmArtifactRefSnapshot):
        raise TypeError('target_artifact_ref must be AlarmArtifactRefSnapshot')
    return {
        'record_schema_version': CONFIGURATION_ADOPTION_RECORD_SCHEMA_VERSION,
        'adoption_id': adoption_id,
        'previous_artifact_ref': (
            None if previous_artifact_ref is None else previous_artifact_ref.as_document()
        ),
        'target_artifact_ref': target_artifact_ref.as_document(),
        'effective_at': effective_at,
        'committed_at': committed_at,
    }


def _require_exact_mapping(
    value: Mapping[str, Any], required: set[str], label: str
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != required:
        raise AlarmPersistenceCorruptionError(f'{label} has invalid fields')
    return value


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f'{name} must be non-empty text without surrounding whitespace')


def _require_utc_timestamp(value: str, name: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(f'{name} must be an ISO-8601 UTC string')
    try:
        timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError(f'{name} must be an ISO-8601 UTC string') from error
    if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
        raise ValueError(f'{name} must be timezone-aware UTC')
    return timestamp


@dataclass(frozen=True, slots=True)
class GroupCommitReference:
    priority_group: str
    commit_id: str
    record_hash: str

    def __post_init__(self) -> None:
        _require_text(self.priority_group, 'priority_group')
        _require_text(self.commit_id, 'commit_id')
        if (
            not isinstance(self.record_hash, str)
            or _RECORD_HASH_PATTERN.fullmatch(self.record_hash) is None
        ):
            raise ValueError('group commit record_hash must be a canonical SHA-256 digest')

    def as_document(self) -> JsonDocument:
        return {
            'priority_group': self.priority_group,
            'commit_id': self.commit_id,
            'record_hash': self.record_hash,
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> GroupCommitReference:
        document = _require_exact_mapping(
            value,
            {'priority_group', 'commit_id', 'record_hash'},
            'group commit reference',
        )
        try:
            return cls(**document)
        except (TypeError, ValueError) as error:
            raise AlarmPersistenceCorruptionError('group commit reference is invalid') from error


@dataclass(frozen=True, slots=True)
class ConfigurationAdoptionRecordV2(ConfigurationAdoptionRecord):
    group_commits: tuple[GroupCommitReference, ...]

    def __post_init__(self) -> None:
        ConfigurationAdoptionRecord.__post_init__(self)
        if not isinstance(self.group_commits, tuple) or not self.group_commits:
            raise ValueError('V2 adoption requires a non-empty tuple of group commits')
        if not all(isinstance(item, GroupCommitReference) for item in self.group_commits):
            raise TypeError('group_commits must contain GroupCommitReference values')
        groups = tuple(ref.priority_group for ref in self.group_commits)
        if groups != tuple(sorted(set(groups))):
            raise ValueError('group_commits must be unique and sorted by priority_group')

    @classmethod
    def create(
        cls,
        *,
        adoption_id: str,
        previous_artifact_ref: AlarmArtifactRefSnapshot | None,
        target_artifact_ref: AlarmArtifactRefSnapshot,
        effective_at: str,
        committed_at: str,
        group_commits: tuple[GroupCommitReference, ...],
    ) -> ConfigurationAdoptionRecordV2:
        unsigned = _unsigned_document_v2(
            adoption_id=adoption_id,
            previous_artifact_ref=previous_artifact_ref,
            target_artifact_ref=target_artifact_ref,
            effective_at=effective_at,
            committed_at=committed_at,
            group_commits=group_commits,
        )
        return cls(
            adoption_id=adoption_id,
            previous_artifact_ref=previous_artifact_ref,
            target_artifact_ref=target_artifact_ref,
            effective_at=effective_at,
            committed_at=committed_at,
            record_hash=build_record_hash(unsigned),
            group_commits=group_commits,
        )

    def unsigned_document(self) -> JsonDocument:
        return _unsigned_document_v2(
            adoption_id=self.adoption_id,
            previous_artifact_ref=self.previous_artifact_ref,
            target_artifact_ref=self.target_artifact_ref,
            effective_at=self.effective_at,
            committed_at=self.committed_at,
            group_commits=self.group_commits,
        )

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> ConfigurationAdoptionRecordV2:
        document = _require_exact_mapping(
            value,
            {
                'record_schema_version',
                'adoption_id',
                'previous_artifact_ref',
                'target_artifact_ref',
                'effective_at',
                'committed_at',
                'record_hash',
                'group_commits',
            },
            'V2 configuration adoption record',
        )
        if document['record_schema_version'] != CONFIGURATION_ADOPTION_RECORD_V2_SCHEMA_VERSION:
            raise AlarmPersistenceCorruptionError('V2 adoption schema version is unsupported')
        previous = document['previous_artifact_ref']
        references = document['group_commits']
        if not isinstance(references, list):
            raise AlarmPersistenceCorruptionError('group_commits must be an array')
        try:
            record = cls(
                adoption_id=document['adoption_id'],
                previous_artifact_ref=(
                    None if previous is None else AlarmArtifactRefSnapshot.from_document(previous)
                ),
                target_artifact_ref=AlarmArtifactRefSnapshot.from_document(
                    document['target_artifact_ref']
                ),
                effective_at=document['effective_at'],
                committed_at=document['committed_at'],
                group_commits=tuple(GroupCommitReference.from_document(ref) for ref in references),
                record_hash=document['record_hash'],
            )
        except (TypeError, ValueError) as error:
            raise AlarmPersistenceCorruptionError(
                'V2 configuration adoption record is invalid'
            ) from error
        if build_record_hash(record.unsigned_document()) != record.record_hash:
            raise AlarmPersistenceCorruptionError('V2 configuration adoption record hash mismatch')
        return record


def _unsigned_document_v2(
    *,
    adoption_id: str,
    previous_artifact_ref: AlarmArtifactRefSnapshot | None,
    target_artifact_ref: AlarmArtifactRefSnapshot,
    effective_at: str,
    committed_at: str,
    group_commits: tuple[GroupCommitReference, ...],
) -> JsonDocument:
    if (
        not isinstance(group_commits, tuple)
        or not group_commits
        or not all(isinstance(item, GroupCommitReference) for item in group_commits)
    ):
        raise ValueError('V2 adoption requires non-empty group commit references')
    document = _unsigned_document(
        adoption_id=adoption_id,
        previous_artifact_ref=previous_artifact_ref,
        target_artifact_ref=target_artifact_ref,
        effective_at=effective_at,
        committed_at=committed_at,
    )
    document['record_schema_version'] = CONFIGURATION_ADOPTION_RECORD_V2_SCHEMA_VERSION
    document['group_commits'] = [item.as_document() for item in group_commits]
    return document
