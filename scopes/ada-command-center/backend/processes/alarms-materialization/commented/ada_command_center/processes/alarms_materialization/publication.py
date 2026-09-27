from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

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
from atlanticus.state import AtomicJsonStore, StateError

DOCUMENT_TYPE = 'ada_command_center_alarm_materialization_result'
SCHEMA_VERSION = 1
READY_DOCUMENT_TYPE = 'ada_command_center_alarm_materialization_ready'
_RESULT_PATTERN = re.compile(r'alarm-materialization-[0-9a-f]{64}')
_SHA256_PATTERN = re.compile(r'[0-9a-f]{64}')


class AlarmMaterializationPublicationError(RuntimeError):
    pass


def _encode(document: object) -> bytes:
    return json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode(
        'utf-8'
    )


def _digest(document: object) -> str:
    return sha256(_encode(document)).hexdigest()


# La identidad del resultado depende de la proyección congelada y de la evidencia exacta, no de una marca temporal.
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


def _resolution_key(candidate: AlarmMaterializationCandidate) -> dict[str, str]:
    return {
        'alarm_configuration_revision': candidate.alarm_configuration_revision,
        'confirmed_tool_catalog_revision': candidate.confirmed_tool_catalog_revision,
    }


# Registramos la procedencia completa para impedir que un resultado se reutilice con evidencia distinta.
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


# B.2 ya resolvió READY o BLOCKED; aquí convertimos su resultado en un manifiesto local específico.
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


def _require_result_id(value: object) -> str:
    if not isinstance(value, str) or _RESULT_PATTERN.fullmatch(value) is None:
        raise AlarmMaterializationPublicationError('Invalid materialization result identity')
    return value


def _require_sha256(value: object) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise AlarmMaterializationPublicationError('Invalid materialization digest')
    return value


def _fsync_directory(path: Path) -> None:
    if os.name == 'nt':
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@dataclass(frozen=True, slots=True)
# Transportamos ambos contratos y el hash del manifiesto para identificar exactamente la versión leída.
class ReadyAlarmMaterialization:
    result_id: str
    runtime: RuntimeAlarmConfiguration
    delivery: DeliveryAlarmConfiguration
    manifest: dict[str, object]
    manifest_sha256: str


# Este almacenamiento conoce el layout local, no utiliza Cosmos ni modifica el estado del Engine.
class LocalAlarmMaterializationResultStore:
    def __init__(self, *, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError('Materialization root must be an absolute Path')
        self._root = root
        self._versions = root / 'versions'
        self._heads = AtomicJsonStore(root_path=root)

    def get(self, *, source_key: str, result_id: str) -> dict[str, object] | None:
        version = self._read_version(source_key=source_key, result_id=result_id)
        return None if version is None else version[0]

    # Primero escribimos una versión completa en un directorio temporal del mismo filesystem; READY no cambia todavía.
    def create(
        self,
        *,
        manifest: dict[str, object],
        runtime: dict[str, object] | None,
        delivery: dict[str, object] | None,
    ) -> dict[str, object]:
        result_id = _require_result_id(manifest.get('result_id'))
        source_key = manifest.get('source_key')
        if not isinstance(source_key, str) or not source_key:
            raise AlarmMaterializationPublicationError('Invalid materialization source key')
        if (runtime is None) != (delivery is None):
            raise AlarmMaterializationPublicationError('Runtime and Delivery must be published together')
        if (manifest.get('status') == 'READY') != (runtime is not None):
            raise AlarmMaterializationPublicationError('Materialization status and artifacts disagree')
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
            # Antes de hacer visible la versión, comprobamos que los codecs pueden reconstruir ambos contratos.
            self._inspect_version(stage, source_key=source_key, result_id=result_id)
            _fsync_directory(stage)
            # El cambio de nombre hace visible una versión íntegra, aún no seleccionada por los consumidores.
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
            raise AlarmMaterializationPublicationError('Published materialization version is missing')
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

    def read_published_ready(self, *, source_key: str) -> ReadyAlarmMaterialization | None:
        head = self._read_head(source_key=source_key)
        if head is None:
            return None
        result = self.read_ready(
            source_key=source_key,
            result_id=head['result_id'],
            expected_manifest_sha256=head['manifest_sha256'],
        )
        if head['resolution_key'] != result.manifest['resolution_key']:
            raise AlarmMaterializationPublicationError('READY pointer resolution key mismatch')
        return result

    def read_ready(
        self,
        *,
        source_key: str,
        result_id: str,
        expected_manifest_sha256: str | None = None,
    ) -> ReadyAlarmMaterialization:
        version = self._read_version(source_key=source_key, result_id=result_id)
        if version is None or version[0]['status'] != 'READY':
            raise AlarmMaterializationPublicationError('READY materialization is unavailable')
        manifest, runtime, delivery, digest = version
        if expected_manifest_sha256 is not None and digest != _require_sha256(
            expected_manifest_sha256
        ):
            raise AlarmMaterializationPublicationError('READY manifest integrity check failed')
        if runtime is None or delivery is None:
            raise AlarmMaterializationPublicationError('READY materialization artifacts are missing')
        return ReadyAlarmMaterialization(
            result_id=result_id,
            runtime=runtime,
            delivery=delivery,
            manifest=manifest,
            manifest_sha256=digest,
        )

    def _read_head(self, *, source_key: str) -> dict[str, object] | None:
        try:
            head = self._heads.read('ready.json')
        except StateError as error:
            raise AlarmMaterializationPublicationError('Could not read local READY pointer') from error
        if head is None:
            return None
        if (
            set(head)
            != {
                'document_type',
                'schema_version',
                'source_key',
                'result_id',
                'resolution_key',
                'manifest_sha256',
            }
            or head.get('document_type') != READY_DOCUMENT_TYPE
            or head.get('schema_version') != SCHEMA_VERSION
            or head.get('source_key') != source_key
            or not isinstance(head.get('resolution_key'), dict)
        ):
            raise AlarmMaterializationPublicationError('Invalid local READY pointer')
        _require_result_id(head.get('result_id'))
        _require_sha256(head.get('manifest_sha256'))
        return head

    # Comprobamos identidad, procedencia, tamaños, hashes y coincidencia de claves antes de devolver contratos.
    def _read_version(
        self, *, source_key: str, result_id: str
    ) -> tuple[
        dict[str, object],
        RuntimeAlarmConfiguration | None,
        DeliveryAlarmConfiguration | None,
        str,
    ] | None:
        path = self._version_path(result_id)
        if not path.exists():
            return None
        return self._inspect_version(path, source_key=source_key, result_id=result_id)

    # La misma verificación sirve para temporales todavía ocultos y para versiones ya publicadas.
    def _inspect_version(
        self, path: Path, *, source_key: str, result_id: str
    ) -> tuple[
        dict[str, object],
        RuntimeAlarmConfiguration | None,
        DeliveryAlarmConfiguration | None,
        str,
    ]:
        if not path.is_dir() or path.is_symlink():
            raise AlarmMaterializationPublicationError('Invalid materialization version directory')
        manifest, digest = self._read_document(path / 'manifest.json')
        provenance = manifest.get('provenance')
        resolution_key = manifest.get('resolution_key')
        if (
            set(manifest)
            != {
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
            or manifest.get('document_type') != DOCUMENT_TYPE
            or manifest.get('schema_version') != SCHEMA_VERSION
            or manifest.get('source_key') != source_key
            or manifest.get('result_id') != result_id
            or manifest.get('status') not in ('READY', 'BLOCKED')
            or not isinstance(provenance, dict)
            or not isinstance(resolution_key, dict)
            or set(resolution_key)
            != {'alarm_configuration_revision', 'confirmed_tool_catalog_revision'}
            or not isinstance(manifest.get('findings'), list)
            or not isinstance(manifest.get('artifacts'), dict)
            or resolution_key.get('alarm_configuration_revision')
            != provenance.get('source_release_id')
            or resolution_key.get('confirmed_tool_catalog_revision')
            != provenance.get('confirmed_tool_catalog_revision')
            or result_id
            != 'alarm-materialization-'
            + _digest(
                {
                    'source_key': source_key,
                    'projection_digest': provenance.get('projection_digest'),
                    'qualification_digest': provenance.get('qualification_digest'),
                }
            )
        ):
            raise AlarmMaterializationPublicationError('Invalid materialization manifest identity')
        # Rechazamos manifiestos incompletos y fechas incoherentes antes de ofrecer una versión al consumidor.
        required_provenance = {
            'source_release_id',
            'source_published_at_utc',
            'confirmed_tool_catalog_revision',
            'projection_digest',
            'qualification_digest',
            'qualification_producer',
            'qualification_evidence_ref',
            'qualified_at_utc',
        }
        if set(provenance) != required_provenance or any(
            not isinstance(value, str) or not value or value.strip() != value
            for value in provenance.values()
        ):
            raise AlarmMaterializationPublicationError('Invalid materialization provenance')
        _require_sha256(provenance['projection_digest'])
        _require_sha256(provenance['qualification_digest'])
        try:
            source_time = datetime.fromisoformat(provenance['source_published_at_utc'])
            qualified_time = datetime.fromisoformat(provenance['qualified_at_utc'])
        except ValueError as error:
            raise AlarmMaterializationPublicationError(
                'Invalid materialization provenance timestamps'
            ) from error
        if (
            source_time.tzinfo is None
            or source_time.utcoffset() is None
            or qualified_time.tzinfo is None
            or qualified_time.utcoffset() is None
            or qualified_time < source_time
        ):
            raise AlarmMaterializationPublicationError('Invalid materialization provenance timestamps')
        # Los diagnósticos también forman parte del contrato publicado, incluso cuando no hay ejecutables.
        if any(
            not isinstance(item, dict)
            or set(item)
            != {'code', 'severity', 'message', 'alarm_identity', 'field_path', 'reference_key'}
            or item['severity'] not in ('BLOCKING', 'WARNING')
            or not isinstance(item['code'], str)
            or not item['code']
            or not isinstance(item['message'], str)
            or not item['message']
            for item in manifest['findings']
        ):
            raise AlarmMaterializationPublicationError('Invalid materialization findings')
        artifacts = manifest['artifacts']
        if manifest['status'] == 'BLOCKED':
            if artifacts or any((path / f'{name}.json').exists() for name in ('runtime', 'delivery')):
                raise AlarmMaterializationPublicationError('BLOCKED result contains executable artifacts')
            if not any(
                isinstance(item, dict) and item.get('severity') == 'BLOCKING'
                for item in manifest['findings']
            ):
                raise AlarmMaterializationPublicationError('BLOCKED materialization findings are invalid')
            return manifest, None, None, digest
        if set(artifacts) != {'runtime', 'delivery'}:
            raise AlarmMaterializationPublicationError('READY materialization artifacts are missing')
        documents: dict[str, dict[str, object]] = {}
        for label in ('runtime', 'delivery'):
            description = artifacts[label]
            if (
                not isinstance(description, dict)
                or set(description) != {'path', 'size_bytes', 'sha256'}
                or description.get('path') != f'{label}.json'
                or not isinstance(description.get('size_bytes'), int)
                or isinstance(description['size_bytes'], bool)
                or description['size_bytes'] <= 0
            ):
                raise AlarmMaterializationPublicationError('Invalid materialization artifact inventory')
            expected_digest = _require_sha256(description.get('sha256'))
            documents[label], actual_digest, size = self._read_document_with_size(
                path / f'{label}.json'
            )
            if actual_digest != expected_digest or size != description['size_bytes']:
                raise AlarmMaterializationPublicationError('READY materialization integrity check failed')
        try:
            runtime = runtime_from_document(documents['runtime'])
            delivery = delivery_from_document(documents['delivery'])
        except (KeyError, TypeError, ValueError) as error:
            raise AlarmMaterializationPublicationError(
                'READY materialization artifact contract is invalid'
            ) from error
        if (
            runtime.resolution_key != delivery.resolution_key
            or documents['runtime'].get('resolution_key') != resolution_key
            or documents['delivery'].get('resolution_key') != resolution_key
            or runtime.resolution_key.alarm_configuration_revision
            != provenance.get('source_release_id')
            or runtime.resolution_key.confirmed_tool_catalog_revision
            != provenance.get('confirmed_tool_catalog_revision')
            or any(
                isinstance(item, dict) and item.get('severity') == 'BLOCKING'
                for item in manifest['findings']
            )
        ):
            raise AlarmMaterializationPublicationError('READY materialization resolution key mismatch')
        return manifest, runtime, delivery, digest

    @staticmethod
    def _read_document(path: Path) -> tuple[dict[str, object], str]:
        document, digest, _ = LocalAlarmMaterializationResultStore._read_document_with_size(path)
        return document, digest

    @staticmethod
    def _read_document_with_size(path: Path) -> tuple[dict[str, object], str, int]:
        try:
            if path.is_symlink():
                raise AlarmMaterializationPublicationError('Materialization artifact must not be a link')
            payload = path.read_bytes()
            document = json.loads(payload)
        except (OSError, UnicodeError, ValueError) as error:
            raise AlarmMaterializationPublicationError('Could not read local materialization artifact') from error
        if not isinstance(document, dict):
            raise AlarmMaterializationPublicationError('Materialization artifact must be an object')
        return document, sha256(payload).hexdigest(), len(payload)

    def _version_path(self, result_id: str) -> Path:
        return self._versions / _require_result_id(result_id)

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


# El publicador valida el candidato y coordina preparación y promoción sin incorporar un segundo backend.
class AlarmMaterializationPublisher:
    def __init__(self, store: LocalAlarmMaterializationResultStore) -> None:
        self._store = store

    # Los resultados preexistentes deben corresponder exactamente al candidato y evidencia actuales.
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

    # READY se cambia con un único documento atómico; esta operación no significa Runtime Adoption.
    def promote_ready(
        self, candidate: AlarmMaterializationCandidate, evidence: AlarmQualificationEvidence
    ) -> bool:
        existing = self.get_existing(candidate, evidence)
        if existing is None or existing['status'] != 'READY':
            raise AlarmMaterializationPublicationError('READY materialization is unavailable')
        return self._store.promote_ready(
            source_key=candidate.source_key.value, result_id=result_id_for(candidate, evidence)
        )

    # BLOCKED conserva diagnóstico; READY escribe y selecciona una pareja coherente de artefactos.
    def publish(
        self,
        candidate: AlarmMaterializationCandidate,
        evidence: AlarmQualificationEvidence,
        resolution: AlarmConfigurationResolution,
    ) -> str:
        manifest, runtime, delivery = _prepare(candidate, evidence, resolution)
        existing = self.get_existing(candidate, evidence)
        if existing is None:
            persisted = self._store.create(
                manifest=manifest, runtime=runtime, delivery=delivery
            )
        else:
            persisted = existing
        _validate_header(persisted, candidate, evidence)
        if (
            {key: value for key, value in persisted.items() if key != 'artifacts'}
            != {key: value for key, value in manifest.items() if key != 'artifacts'}
        ):
            raise AlarmMaterializationPublicationError(
                'Materialization result identity conflicts with existing content'
            )
        if resolution.status is AlarmResolutionStatus.READY:
            # Si la misma identidad ya existe, ambos artefactos deben coincidir con el nuevo resultado.
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
        raise AlarmMaterializationPublicationError('Stored materialization result identity is invalid')
