# Contratos durables de identidad, procedencia, manifiesto y puntero READY de la materialización.
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from types import MappingProxyType

from ada.alarms.core import AlarmResolutionKey
from ada.alarms.materialization.resolution import (
    AlarmResolutionFinding,
    AlarmResolutionFindingSeverity,
    AlarmResolutionStatus,
)
from ada.contracts.alarms import AlarmIdentity

DOCUMENT_TYPE = 'ada_alarm_engine_materialization_result'
READY_DOCUMENT_TYPE = 'ada_alarm_engine_materialization_ready'
SCHEMA_VERSION = 1
_RESULT_PATTERN = re.compile(r'alarm-materialization-[0-9a-f]{64}')
_SHA256_PATTERN = re.compile(r'[0-9a-f]{64}')
_ARTIFACT_LABELS = ('engine', 'modeler', 'delivery')


# Serialización canónica usada para identidades deterministas.
def canonical_json_bytes(document: Mapping[str, object]) -> bytes:
    if not isinstance(document, Mapping):
        raise TypeError('document must be a mapping')
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')


# Identidad estable del resultado para la misma fuente y evidencia de qualification.
def materialization_result_id(
    *,
    source_key: str,
    projection_digest: str,
    qualification_digest: str,
) -> str:
    _require_non_empty_string(source_key, 'source_key')
    _require_sha256(projection_digest, 'projection_digest')
    _require_sha256(qualification_digest, 'qualification_digest')
    digest = sha256(
        canonical_json_bytes(
            {
                'source_key': source_key,
                'projection_digest': projection_digest,
                'qualification_digest': qualification_digest,
            }
        )
    ).hexdigest()
    return f'alarm-materialization-{digest}'


@dataclass(frozen=True, slots=True)
# Evidencia que vincula el resultado con release, Tool Catalog y qualification.
class AlarmMaterializationProvenance:
    source_release_id: str
    source_published_at_utc: str
    confirmed_tool_catalog_revision: str
    projection_digest: str
    qualification_digest: str
    qualification_producer: str
    qualification_evidence_ref: str
    qualified_at_utc: str

    def __post_init__(self) -> None:
        for field_name in (
            'source_release_id',
            'source_published_at_utc',
            'confirmed_tool_catalog_revision',
            'projection_digest',
            'qualification_digest',
            'qualification_producer',
            'qualification_evidence_ref',
            'qualified_at_utc',
        ):
            _require_non_empty_string(getattr(self, field_name), field_name)
        _require_sha256(self.projection_digest, 'projection_digest')
        _require_sha256(self.qualification_digest, 'qualification_digest')
        source_time = _require_aware_datetime(
            self.source_published_at_utc,
            'source_published_at_utc',
        )
        qualified_time = _require_aware_datetime(self.qualified_at_utc, 'qualified_at_utc')
        if qualified_time < source_time:
            raise ValueError('qualified_at_utc must not predate source_published_at_utc')

    def to_document(self) -> dict[str, object]:
        return {
            'source_release_id': self.source_release_id,
            'source_published_at_utc': self.source_published_at_utc,
            'confirmed_tool_catalog_revision': self.confirmed_tool_catalog_revision,
            'projection_digest': self.projection_digest,
            'qualification_digest': self.qualification_digest,
            'qualification_producer': self.qualification_producer,
            'qualification_evidence_ref': self.qualification_evidence_ref,
            'qualified_at_utc': self.qualified_at_utc,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> AlarmMaterializationProvenance:
        required = {
            'source_release_id',
            'source_published_at_utc',
            'confirmed_tool_catalog_revision',
            'projection_digest',
            'qualification_digest',
            'qualification_producer',
            'qualification_evidence_ref',
            'qualified_at_utc',
        }
        if not isinstance(document, Mapping) or set(document) != required:
            raise ValueError('materialization provenance contract is invalid')
        return cls(**{key: document[key] for key in required})


@dataclass(frozen=True, slots=True)
# Inventario verificable de un artifact físico publicado.
class AlarmMaterializationArtifact:
    path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        _require_non_empty_string(self.path, 'path')
        if '/' in self.path or '\\' in self.path or self.path in {'.', '..'}:
            raise ValueError('path must be a single relative file name')
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int):
            raise TypeError('size_bytes must be an int')
        if self.size_bytes <= 0:
            raise ValueError('size_bytes must be greater than zero')
        _require_sha256(self.sha256, 'sha256')

    def to_document(self) -> dict[str, object]:
        return {
            'path': self.path,
            'size_bytes': self.size_bytes,
            'sha256': self.sha256,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> AlarmMaterializationArtifact:
        if not isinstance(document, Mapping) or set(document) != {'path', 'size_bytes', 'sha256'}:
            raise ValueError('materialization artifact contract is invalid')
        return cls(
            path=document['path'],
            size_bytes=document['size_bytes'],
            sha256=document['sha256'],
        )


@dataclass(frozen=True, slots=True)
# Contrato principal: READY exige tres artifacts; BLOCKED no permite ninguno.
class AlarmMaterializationManifest:
    source_key: str
    result_id: str
    status: AlarmResolutionStatus
    resolution_key: AlarmResolutionKey
    provenance: AlarmMaterializationProvenance
    findings: tuple[AlarmResolutionFinding, ...]
    artifacts: Mapping[str, AlarmMaterializationArtifact]

    def __post_init__(self) -> None:
        _require_non_empty_string(self.source_key, 'source_key')
        _require_result_id(self.result_id)
        if not isinstance(self.status, AlarmResolutionStatus):
            raise TypeError('status must be an AlarmResolutionStatus')
        if not isinstance(self.resolution_key, AlarmResolutionKey):
            raise TypeError('resolution_key must be an AlarmResolutionKey')
        if not isinstance(self.provenance, AlarmMaterializationProvenance):
            raise TypeError('provenance must be an AlarmMaterializationProvenance')
        if not isinstance(self.findings, tuple):
            raise TypeError('findings must be a tuple')
        for finding in self.findings:
            if not isinstance(finding, AlarmResolutionFinding):
                raise TypeError('findings must contain AlarmResolutionFinding values')
        if not isinstance(self.artifacts, Mapping):
            raise TypeError('artifacts must be a mapping')
        normalized: dict[str, AlarmMaterializationArtifact] = {}
        for label, artifact in self.artifacts.items():
            if label not in _ARTIFACT_LABELS:
                raise ValueError('artifacts contain an unsupported label')
            if not isinstance(artifact, AlarmMaterializationArtifact):
                raise TypeError('artifacts must contain AlarmMaterializationArtifact values')
            if artifact.path != f'{label}.json':
                raise ValueError('artifact path does not match its label')
            normalized[label] = artifact
        object.__setattr__(self, 'artifacts', MappingProxyType(normalized))
        expected_result_id = materialization_result_id(
            source_key=self.source_key,
            projection_digest=self.provenance.projection_digest,
            qualification_digest=self.provenance.qualification_digest,
        )
        if self.result_id != expected_result_id:
            raise ValueError('result_id does not match publication identity')
        if self.resolution_key.alarm_configuration_revision != self.provenance.source_release_id:
            raise ValueError('resolution key does not match source release')
        if (
            self.resolution_key.confirmed_tool_catalog_revision
            != self.provenance.confirmed_tool_catalog_revision
        ):
            raise ValueError('resolution key does not match confirmed Tool Catalog revision')
        blocking = any(
            finding.severity is AlarmResolutionFindingSeverity.BLOCKING for finding in self.findings
        )
        if self.status is AlarmResolutionStatus.READY:
            if blocking:
                raise ValueError('READY manifest must not contain BLOCKING findings')
            if set(normalized) != set(_ARTIFACT_LABELS):
                raise ValueError('READY manifest requires Engine, Modeler, and Delivery artifacts')
            return
        if not blocking:
            raise ValueError('BLOCKED manifest requires at least one BLOCKING finding')
        if normalized:
            raise ValueError('BLOCKED manifest must not contain artifacts')

    def to_document(self) -> dict[str, object]:
        return {
            'document_type': DOCUMENT_TYPE,
            'schema_version': SCHEMA_VERSION,
            'source_key': self.source_key,
            'result_id': self.result_id,
            'status': self.status.value,
            'resolution_key': _resolution_key_to_document(self.resolution_key),
            'provenance': self.provenance.to_document(),
            'findings': [_finding_to_document(finding) for finding in self.findings],
            'artifacts': {
                label: self.artifacts[label].to_document()
                for label in _ARTIFACT_LABELS
                if label in self.artifacts
            },
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> AlarmMaterializationManifest:
        required = {
            'document_type',
            'schema_version',
            'source_key',
            'result_id',
            'status',
            'resolution_key',
            'provenance',
            'findings',
            'artifacts',
        }
        if not isinstance(document, Mapping) or set(document) != required:
            raise ValueError('materialization manifest contract is invalid')
        if (
            document['document_type'] != DOCUMENT_TYPE
            or document['schema_version'] != SCHEMA_VERSION
        ):
            raise ValueError('materialization manifest identity is invalid')
        findings_document = document['findings']
        artifacts_document = document['artifacts']
        if not isinstance(findings_document, list) or not isinstance(artifacts_document, Mapping):
            raise ValueError('materialization manifest contract is invalid')
        return cls(
            source_key=document['source_key'],
            result_id=document['result_id'],
            status=AlarmResolutionStatus(document['status']),
            resolution_key=_resolution_key_from_document(document['resolution_key']),
            provenance=AlarmMaterializationProvenance.from_document(document['provenance']),
            findings=tuple(_finding_from_document(item) for item in findings_document),
            artifacts={
                label: AlarmMaterializationArtifact.from_document(artifact)
                for label, artifact in artifacts_document.items()
            },
        )


@dataclass(frozen=True, slots=True)
# Head efectivo que apunta únicamente a una versión READY completa.
class AlarmMaterializationReadyPointer:
    source_key: str
    result_id: str
    resolution_key: AlarmResolutionKey
    manifest_sha256: str

    def __post_init__(self) -> None:
        _require_non_empty_string(self.source_key, 'source_key')
        _require_result_id(self.result_id)
        if not isinstance(self.resolution_key, AlarmResolutionKey):
            raise TypeError('resolution_key must be an AlarmResolutionKey')
        _require_sha256(self.manifest_sha256, 'manifest_sha256')

    def to_document(self) -> dict[str, object]:
        return {
            'document_type': READY_DOCUMENT_TYPE,
            'schema_version': SCHEMA_VERSION,
            'source_key': self.source_key,
            'result_id': self.result_id,
            'resolution_key': _resolution_key_to_document(self.resolution_key),
            'manifest_sha256': self.manifest_sha256,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, object]) -> AlarmMaterializationReadyPointer:
        required = {
            'document_type',
            'schema_version',
            'source_key',
            'result_id',
            'resolution_key',
            'manifest_sha256',
        }
        if not isinstance(document, Mapping) or set(document) != required:
            raise ValueError('READY pointer contract is invalid')
        if (
            document['document_type'] != READY_DOCUMENT_TYPE
            or document['schema_version'] != SCHEMA_VERSION
        ):
            raise ValueError('READY pointer identity is invalid')
        return cls(
            source_key=document['source_key'],
            result_id=document['result_id'],
            resolution_key=_resolution_key_from_document(document['resolution_key']),
            manifest_sha256=document['manifest_sha256'],
        )


def _resolution_key_to_document(key: AlarmResolutionKey) -> dict[str, object]:
    return {
        'alarm_configuration_revision': key.alarm_configuration_revision,
        'confirmed_tool_catalog_revision': key.confirmed_tool_catalog_revision,
    }


def _resolution_key_from_document(document: Mapping[str, object]) -> AlarmResolutionKey:
    if not isinstance(document, Mapping) or set(document) != {
        'alarm_configuration_revision',
        'confirmed_tool_catalog_revision',
    }:
        raise ValueError('resolution_key contract is invalid')
    return AlarmResolutionKey(
        alarm_configuration_revision=document['alarm_configuration_revision'],
        confirmed_tool_catalog_revision=document['confirmed_tool_catalog_revision'],
    )


def _finding_to_document(finding: AlarmResolutionFinding) -> dict[str, object]:
    return {
        'code': finding.code,
        'severity': finding.severity.value,
        'message': finding.message,
        'alarm_identity': (
            None
            if finding.alarm_identity is None
            else {
                'family_key': finding.alarm_identity.family_key,
                'alarm_key': finding.alarm_identity.alarm_key,
            }
        ),
        'field_path': finding.field_path,
        'reference_key': finding.reference_key,
    }


def _finding_from_document(document: Mapping[str, object]) -> AlarmResolutionFinding:
    required = {
        'code',
        'severity',
        'message',
        'alarm_identity',
        'field_path',
        'reference_key',
    }
    if not isinstance(document, Mapping) or set(document) != required:
        raise ValueError('materialization finding contract is invalid')
    identity_document = document['alarm_identity']
    if identity_document is not None:
        if not isinstance(identity_document, Mapping) or set(identity_document) != {
            'family_key',
            'alarm_key',
        }:
            raise ValueError('materialization finding identity is invalid')
        identity = AlarmIdentity(
            family_key=identity_document['family_key'],
            alarm_key=identity_document['alarm_key'],
        )
    else:
        identity = None
    return AlarmResolutionFinding(
        code=document['code'],
        severity=AlarmResolutionFindingSeverity(document['severity']),
        message=document['message'],
        alarm_identity=identity,
        field_path=document['field_path'],
        reference_key=document['reference_key'],
    )


def _require_result_id(value: object) -> str:
    if not isinstance(value, str) or _RESULT_PATTERN.fullmatch(value) is None:
        raise ValueError('result_id must identify one Alarm materialization result')
    return value


def _require_sha256(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f'{name} must be a lowercase SHA-256 digest')
    return value


def _require_aware_datetime(value: str, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f'{name} must be an ISO datetime') from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f'{name} must be timezone-aware')
    return parsed


def _require_non_empty_string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f'{name} must be a string')
    if not value or value.strip() != value:
        raise ValueError(f'{name} must be non-empty text without surrounding whitespace')
    return value
