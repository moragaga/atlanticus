from __future__ import annotations

import os
import shutil
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from ada_command_center.alarms.materialization import (
    AlarmConfigurationResolution,
    AlarmResolutionStatus,
)
from ada_command_center.alarms.materialization.codec import (
    delivery_to_document,
    runtime_to_document,
)
from ada_command_center.alarms.materialization.local_reader import (
    DOCUMENT_TYPE,
    READY_DOCUMENT_TYPE,
    SCHEMA_VERSION,
    AlarmMaterializationPublicationError,
    LocalAlarmMaterializationReader,
    ReadyAlarmMaterialization,
    materialization_result_id,
)
from ada_command_center.processes.alarms_materialization.candidate import (
    AlarmMaterializationCandidate,
)
from ada_command_center.processes.alarms_materialization.qualification import (
    AlarmQualificationEvidence,
)
from atlanticus.state import AtomicJsonStore, StateError


def result_id_for(
    candidate: AlarmMaterializationCandidate, evidence: AlarmQualificationEvidence
) -> str:
    return materialization_result_id(
        source_key=candidate.source_key.value,
        projection_digest=candidate.fingerprint,
        qualification_digest=evidence.digest,
    )


def _resolution_key(candidate: AlarmMaterializationCandidate) -> dict[str, str]:
    return {
        'alarm_configuration_revision': candidate.alarm_configuration_revision,
        'confirmed_tool_catalog_revision': candidate.confirmed_tool_catalog_revision,
    }


def _provenance(
    candidate: AlarmMaterializationCandidate, evidence: AlarmQualificationEvidence
) -> dict[str, str]:
    return {
        'source_release_id': candidate.alarm_configuration_revision,
        'source_published_at_utc': candidate.source_release.published_at_utc.isoformat(),
        'confirmed_tool_catalog_revision': candidate.confirmed_tool_catalog_revision,
        'projection_digest': candidate.fingerprint,
        'qualification_digest': evidence.digest,
        'qualification_producer': evidence.producer,
        'qualification_evidence_ref': evidence.evidence_ref,
        'qualified_at_utc': evidence.qualified_at_utc,
    }


def _prepare(
    candidate: AlarmMaterializationCandidate,
    evidence: AlarmQualificationEvidence,
    resolution: AlarmConfigurationResolution,
) -> tuple[dict[str, object], dict[str, object] | None, dict[str, object] | None]:
    if (
        resolution.resolution_key.alarm_configuration_revision
        != candidate.alarm_configuration_revision
        or resolution.resolution_key.confirmed_tool_catalog_revision
        != candidate.confirmed_tool_catalog_revision
    ):
        raise AlarmMaterializationPublicationError('Resolution key does not match candidate')
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
    manifest: dict[str, object] = {
        'document_type': DOCUMENT_TYPE,
        'schema_version': SCHEMA_VERSION,
        'source_key': candidate.source_key.value,
        'result_id': result_id_for(candidate, evidence),
        'status': resolution.status.value,
        'resolution_key': _resolution_key(candidate),
        'provenance': _provenance(candidate, evidence),
        'findings': findings,
        'artifacts': {},
    }
    if resolution.status is AlarmResolutionStatus.BLOCKED:
        return manifest, None, None
    if resolution.status is not AlarmResolutionStatus.READY:
        raise AlarmMaterializationPublicationError('Unsupported Alarm resolution status')
    if resolution.runtime_configuration is None or resolution.delivery_configuration is None:
        raise AlarmMaterializationPublicationError('READY resolution requires both configurations')
    return (
        manifest,
        runtime_to_document(resolution.runtime_configuration),
        delivery_to_document(resolution.delivery_configuration),
    )


def _fsync_directory(path: Path) -> None:
    if os.name == 'nt':
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class LocalAlarmMaterializationResultStore(LocalAlarmMaterializationReader):
    def __init__(self, *, root: Path) -> None:
        super().__init__(root=root)
        self._heads = AtomicJsonStore(root_path=root)

    def get(self, *, source_key: str, result_id: str) -> dict[str, object] | None:
        version = self._read_version(source_key=source_key, result_id=result_id)
        return None if version is None else version[0]

    def create(
        self,
        *,
        manifest: dict[str, object],
        runtime: dict[str, object] | None,
        delivery: dict[str, object] | None,
    ) -> dict[str, object]:
        result_id = manifest.get('result_id')
        self._version_path(result_id)
        source_key = manifest.get('source_key')
        if not isinstance(source_key, str) or not source_key:
            raise AlarmMaterializationPublicationError('Invalid materialization source key')
        if (runtime is None) != (delivery is None):
            raise AlarmMaterializationPublicationError(
                'Runtime and Delivery must be published together'
            )
        if (manifest.get('status') == 'READY') != (runtime is not None):
            raise AlarmMaterializationPublicationError(
                'Materialization status and artifacts disagree'
            )
        existing = self.get(source_key=source_key, result_id=result_id)
        if existing is not None:
            return existing
        stage: Path | None = None
        try:
            self._versions.mkdir(parents=True, exist_ok=True)
            self._remove_orphan_stages(result_id)
            stage = self._versions / f'.{result_id}.{uuid4().hex}.staging'
            stage.mkdir(exist_ok=False)
            writer = AtomicJsonStore(root_path=stage, max_document_bytes=None)
            prepared = dict(manifest)
            artifacts: dict[str, object] = {}
            for label, document in (('runtime', runtime), ('delivery', delivery)):
                if document is None:
                    continue
                filename = f'{label}.json'
                writer.replace(filename, document)
                payload = (stage / filename).read_bytes()
                artifacts[label] = {
                    'path': filename,
                    'size_bytes': len(payload),
                    'sha256': sha256(payload).hexdigest(),
                }
            prepared['artifacts'] = artifacts
            writer.replace('manifest.json', prepared)
            self._inspect_version(stage, source_key=source_key, result_id=result_id)
            _fsync_directory(stage)
            os.rename(stage, self._version_path(result_id))
            stage = None
            _fsync_directory(self._versions)
        except (OSError, StateError) as error:
            raise AlarmMaterializationPublicationError(
                'Could not publish local Alarm materialization version'
            ) from error
        finally:
            if stage is not None:
                shutil.rmtree(stage, ignore_errors=True)
        published = self.get(source_key=source_key, result_id=result_id)
        if published is None:
            raise AlarmMaterializationPublicationError(
                'Published materialization version is missing'
            )
        return published

    def promote_ready(self, *, source_key: str, result_id: str) -> bool:
        version = self._read_version(source_key=source_key, result_id=result_id)
        if version is None or version[0]['status'] != 'READY':
            raise AlarmMaterializationPublicationError('READY materialization is unavailable')
        manifest, _, _, manifest_sha256 = version
        head = {
            'document_type': READY_DOCUMENT_TYPE,
            'schema_version': SCHEMA_VERSION,
            'source_key': source_key,
            'result_id': result_id,
            'resolution_key': manifest['resolution_key'],
            'manifest_sha256': manifest_sha256,
        }
        current = self._read_head(source_key=source_key)
        if current == head:
            return False
        try:
            self._heads.replace('ready.json', head)
        except StateError as error:
            raise AlarmMaterializationPublicationError(
                'Could not promote local READY materialization'
            ) from error
        return True

    def is_current_ready(self, *, source_key: str, result_id: str) -> bool:
        current = self.read_published_ready(source_key=source_key)
        return current is not None and current.result_id == result_id

    def _remove_orphan_stages(self, result_id: str) -> None:
        for stage in self._versions.glob(f'.{result_id}.*.staging'):
            if stage.is_symlink() or not stage.is_dir():
                raise AlarmMaterializationPublicationError('Invalid orphan staging directory')
            try:
                shutil.rmtree(stage)
            except OSError as error:
                raise AlarmMaterializationPublicationError(
                    'Could not remove orphan materialization staging directory'
                ) from error


class AlarmMaterializationPublisher:
    def __init__(self, store: LocalAlarmMaterializationResultStore) -> None:
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

    def is_current_ready(
        self, candidate: AlarmMaterializationCandidate, evidence: AlarmQualificationEvidence
    ) -> bool:
        return self._store.is_current_ready(
            source_key=candidate.source_key.value, result_id=result_id_for(candidate, evidence)
        )

    def promote_ready(
        self, candidate: AlarmMaterializationCandidate, evidence: AlarmQualificationEvidence
    ) -> bool:
        existing = self.get_existing(candidate, evidence)
        if existing is None or existing['status'] != 'READY':
            raise AlarmMaterializationPublicationError('READY materialization is unavailable')
        return self._store.promote_ready(
            source_key=candidate.source_key.value, result_id=result_id_for(candidate, evidence)
        )

    def publish(
        self,
        candidate: AlarmMaterializationCandidate,
        evidence: AlarmQualificationEvidence,
        resolution: AlarmConfigurationResolution,
    ) -> str:
        manifest, runtime, delivery = _prepare(candidate, evidence, resolution)
        existing = self.get_existing(candidate, evidence)
        if existing is None:
            persisted = self._store.create(manifest=manifest, runtime=runtime, delivery=delivery)
        else:
            persisted = existing
        _validate_header(persisted, candidate, evidence)
        if {key: value for key, value in persisted.items() if key != 'artifacts'} != {
            key: value for key, value in manifest.items() if key != 'artifacts'
        }:
            raise AlarmMaterializationPublicationError(
                'Materialization result identity conflicts with existing content'
            )
        if resolution.status is AlarmResolutionStatus.READY:
            stored = self._store.read_ready(
                source_key=candidate.source_key.value, result_id=manifest['result_id']
            )
            if (
                runtime_to_document(stored.runtime) != runtime
                or delivery_to_document(stored.delivery) != delivery
            ):
                raise AlarmMaterializationPublicationError(
                    'Materialization result identity conflicts with existing artifacts'
                )
            self._store.promote_ready(
                source_key=candidate.source_key.value, result_id=manifest['result_id']
            )
        return manifest['result_id']

    def read_ready(
        self,
        *,
        source_key: str,
        result_id: str,
        expected_manifest_sha256: str | None = None,
    ) -> ReadyAlarmMaterialization:
        return self._store.read_ready(
            source_key=source_key,
            result_id=result_id,
            expected_manifest_sha256=expected_manifest_sha256,
        )

    def read_published_ready(self, *, source_key: str) -> ReadyAlarmMaterialization | None:
        return self._store.read_published_ready(source_key=source_key)


def _validate_header(
    manifest: dict[str, object],
    candidate: AlarmMaterializationCandidate,
    evidence: AlarmQualificationEvidence,
) -> None:
    if (
        manifest.get('result_id') != result_id_for(candidate, evidence)
        or manifest.get('source_key') != candidate.source_key.value
        or manifest.get('document_type') != DOCUMENT_TYPE
        or manifest.get('schema_version') != SCHEMA_VERSION
        or manifest.get('status') not in ('READY', 'BLOCKED')
        or manifest.get('resolution_key') != _resolution_key(candidate)
        or manifest.get('provenance') != _provenance(candidate, evidence)
    ):
        raise AlarmMaterializationPublicationError(
            'Stored materialization result identity is invalid'
        )
