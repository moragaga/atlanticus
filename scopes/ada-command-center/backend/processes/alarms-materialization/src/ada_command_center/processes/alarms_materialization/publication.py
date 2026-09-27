from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from ada_command_center.alarms.materialization import (
    AlarmConfigurationResolution,
    AlarmResolutionStatus,
    DeliveryAlarmConfiguration,
    RuntimeAlarmConfiguration,
)
from ada_command_center.processes.alarms_materialization.candidate import (
    AlarmMaterializationCandidate,
)
from ada_command_center.processes.alarms_materialization.codec import (
    delivery_from_document,
    delivery_to_document,
    runtime_from_document,
    runtime_to_document,
)
from ada_command_center.processes.alarms_materialization.qualification import (
    AlarmQualificationEvidence,
)
from atlanticus.connectivity.cosmos import CosmosConflictError, CosmosError

DOCUMENT_TYPE = 'ada_command_center_alarm_materialization_result'
SCHEMA_VERSION = 1
MAX_DOCUMENT_BYTES = 1_800_000


class AlarmMaterializationPublicationError(RuntimeError):
    pass


class AlarmMaterializationResultStore(Protocol):
    def get(self, *, source_key: str, result_id: str) -> dict[str, object] | None: ...
    def create(self, document: dict[str, object]) -> dict[str, object]: ...


def _encode(document: object) -> bytes:
    return json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode(
        'utf-8'
    )


def _digest(document: object) -> str:
    return sha256(_encode(document)).hexdigest()


def result_id_for(
    candidate: AlarmMaterializationCandidate, evidence: AlarmQualificationEvidence
) -> str:
    return 'alarm-materialization-' + _digest(
        {
            'source_key': candidate.source_key.value,
            'projection_digest': candidate.fingerprint,
            'qualification_digest': evidence.digest,
        }
    )


def _prepare(
    candidate: AlarmMaterializationCandidate,
    evidence: AlarmQualificationEvidence,
    resolution: AlarmConfigurationResolution,
) -> dict[str, object]:
    if (
        resolution.resolution_key.alarm_configuration_revision
        != candidate.alarm_configuration_revision
        or resolution.resolution_key.confirmed_tool_catalog_revision
        != candidate.confirmed_tool_catalog_revision
    ):
        raise AlarmMaterializationPublicationError('Resolution key does not match candidate')
    manifest: dict[str, object] = {
        'source_key': candidate.source_key.value,
        'source_release_id': candidate.alarm_configuration_revision,
        'source_published_at_utc': candidate.source_release.published_at_utc.isoformat(),
        'confirmed_tool_catalog_revision': candidate.confirmed_tool_catalog_revision,
        'projection_digest': candidate.fingerprint,
        'qualification_digest': evidence.digest,
        'qualification_producer': evidence.producer,
        'qualification_evidence_ref': evidence.evidence_ref,
        'qualified_at_utc': evidence.qualified_at_utc,
    }
    findings = [
        {
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
        for finding in resolution.findings
    ]
    document: dict[str, object] = {
        'id': result_id_for(candidate, evidence),
        'partition_key': candidate.source_key.value,
        'document_type': DOCUMENT_TYPE,
        'schema_version': SCHEMA_VERSION,
        'status': resolution.status.value,
        'resolution_key': {
            'alarm_configuration_revision': resolution.resolution_key.alarm_configuration_revision,
            'confirmed_tool_catalog_revision': (
                resolution.resolution_key.confirmed_tool_catalog_revision
            ),
        },
        'manifest': manifest,
        'findings': findings,
        'runtime': None,
        'delivery': None,
    }
    if resolution.status is AlarmResolutionStatus.READY:
        runtime = runtime_to_document(resolution.runtime_configuration)
        delivery = delivery_to_document(resolution.delivery_configuration)
        manifest['runtime_digest'] = _digest(runtime)
        manifest['delivery_digest'] = _digest(delivery)
        document['runtime'] = runtime
        document['delivery'] = delivery
    if len(_encode(document)) > MAX_DOCUMENT_BYTES:
        raise AlarmMaterializationPublicationError(
            'Alarm materialization result exceeds single-document safety limit'
        )
    return document


@dataclass(frozen=True, slots=True)
class ReadyAlarmMaterialization:
    result_id: str
    runtime: RuntimeAlarmConfiguration
    delivery: DeliveryAlarmConfiguration
    manifest: dict[str, object]


class CosmosAlarmMaterializationResultStore:
    def __init__(self, *, client: object, container_name: str) -> None:
        if not isinstance(container_name, str) or not container_name.strip():
            raise ValueError('Materialization output container name is required')
        self._client = client
        self._container_name = container_name

    def get(self, *, source_key: str, result_id: str) -> dict[str, object] | None:
        try:
            return self._client.find_item(
                container_name=self._container_name,
                item_id=result_id,
                partition_key=source_key,
            )
        except CosmosError as error:
            raise AlarmMaterializationPublicationError(
                'Could not read Alarm materialization result'
            ) from error

    def create(self, document: dict[str, object]) -> dict[str, object]:
        try:
            return self._client.create_item(container_name=self._container_name, item=document)
        except CosmosConflictError:
            existing = self.get(source_key=document['partition_key'], result_id=document['id'])
            if existing is None or _user_document(existing) != document:
                raise AlarmMaterializationPublicationError(
                    'Alarm materialization result identity conflicts with existing content'
                ) from None
            return existing
        except CosmosError as error:
            raise AlarmMaterializationPublicationError(
                'Could not publish Alarm materialization result'
            ) from error


def _user_document(document: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in document.items() if not key.startswith('_')}


class AlarmMaterializationPublisher:
    def __init__(self, store: AlarmMaterializationResultStore) -> None:
        self._store = store

    def get_existing(
        self, candidate: AlarmMaterializationCandidate, evidence: AlarmQualificationEvidence
    ) -> dict[str, object] | None:
        existing = self._store.get(
            source_key=candidate.source_key.value,
            result_id=result_id_for(candidate, evidence),
        )
        if existing is not None:
            _validate_header(existing, candidate, evidence)
        return existing

    def publish(
        self,
        candidate: AlarmMaterializationCandidate,
        evidence: AlarmQualificationEvidence,
        resolution: AlarmConfigurationResolution,
    ) -> str:
        expected = _prepare(candidate, evidence, resolution)
        existing = self._store.get(source_key=candidate.source_key.value, result_id=expected['id'])
        if existing is not None:
            if _user_document(existing) != expected:
                raise AlarmMaterializationPublicationError(
                    'Alarm materialization result identity conflicts with existing content'
                )
            return expected['id']
        published = self._store.create(expected)
        if _user_document(published) != expected:
            raise AlarmMaterializationPublicationError(
                'Persisted Alarm materialization result differs from prepared result'
            )
        return expected['id']

    def read_ready(self, *, source_key: str, result_id: str) -> ReadyAlarmMaterialization:
        document = self._store.get(source_key=source_key, result_id=result_id)
        if document is None or document.get('status') != AlarmResolutionStatus.READY.value:
            raise AlarmMaterializationPublicationError('READY materialization is unavailable')
        if (
            document.get('id') != result_id
            or document.get('partition_key') != source_key
            or document.get('document_type') != DOCUMENT_TYPE
            or document.get('schema_version') != SCHEMA_VERSION
        ):
            raise AlarmMaterializationPublicationError(
                'Materialization identity or schema is invalid'
            )
        manifest = document.get('manifest')
        runtime = document.get('runtime')
        delivery = document.get('delivery')
        if (
            not isinstance(manifest, dict)
            or not isinstance(runtime, dict)
            or not isinstance(delivery, dict)
        ):
            raise AlarmMaterializationPublicationError(
                'READY materialization artifacts are missing'
            )
        if (
            manifest.get('source_key') != source_key
            or result_id
            != 'alarm-materialization-'
            + _digest(
                {
                    'source_key': source_key,
                    'projection_digest': manifest.get('projection_digest'),
                    'qualification_digest': manifest.get('qualification_digest'),
                }
            )
            or manifest.get('runtime_digest') != _digest(runtime)
            or manifest.get('delivery_digest') != _digest(delivery)
        ):
            raise AlarmMaterializationPublicationError(
                'READY materialization integrity check failed'
            )
        try:
            runtime_value = runtime_from_document(runtime)
            delivery_value = delivery_from_document(delivery)
        except (ValueError, TypeError, KeyError) as error:
            raise AlarmMaterializationPublicationError(
                'READY materialization artifact contract is invalid'
            ) from error
        if (
            runtime_value.resolution_key != delivery_value.resolution_key
            or document.get('resolution_key') != runtime['resolution_key']
            or document.get('resolution_key') != delivery['resolution_key']
            or manifest.get('source_release_id')
            != runtime_value.resolution_key.alarm_configuration_revision
            or manifest.get('confirmed_tool_catalog_revision')
            != runtime_value.resolution_key.confirmed_tool_catalog_revision
        ):
            raise AlarmMaterializationPublicationError(
                'READY materialization resolution key mismatch'
            )
        return ReadyAlarmMaterialization(
            result_id=result_id,
            runtime=runtime_value,
            delivery=delivery_value,
            manifest=manifest,
        )


def _validate_header(
    document: dict[str, object],
    candidate: AlarmMaterializationCandidate,
    evidence: AlarmQualificationEvidence,
) -> None:
    manifest = document.get('manifest')
    if (
        document.get('id') != result_id_for(candidate, evidence)
        or document.get('partition_key') != candidate.source_key.value
        or document.get('document_type') != DOCUMENT_TYPE
        or document.get('schema_version') != SCHEMA_VERSION
        or document.get('status') not in ('READY', 'BLOCKED')
        or not isinstance(manifest, dict)
        or manifest.get('projection_digest') != candidate.fingerprint
        or manifest.get('qualification_digest') != evidence.digest
        or manifest.get('source_release_id') != candidate.alarm_configuration_revision
        or manifest.get('confirmed_tool_catalog_revision')
        != candidate.confirmed_tool_catalog_revision
        or document.get('resolution_key')
        != {
            'alarm_configuration_revision': candidate.alarm_configuration_revision,
            'confirmed_tool_catalog_revision': candidate.confirmed_tool_catalog_revision,
        }
    ):
        raise AlarmMaterializationPublicationError(
            'Stored materialization result identity is invalid'
        )
    if document['status'] == 'BLOCKED':
        findings = document.get('findings')
        if (
            document.get('runtime') is not None
            or document.get('delivery') is not None
            or not isinstance(findings, list)
            or not any(
                isinstance(item, dict) and item.get('severity') == 'BLOCKING' for item in findings
            )
        ):
            raise AlarmMaterializationPublicationError('Stored BLOCKED result contract is invalid')
