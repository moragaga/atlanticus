# Persistencia local atómica de versiones READY/BLOCKED y lectura con verificación de integridad.
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from ada.alarms.materialization import (
    AlarmConfigurationResolution,
    AlarmMaterializationArtifact,
    AlarmMaterializationManifest,
    AlarmMaterializationProvenance,
    AlarmMaterializationReadyPointer,
    AlarmResolutionStatus,
    DeliveryAlarmConfiguration,
    EngineAlarmConfiguration,
    ModelerAlarmConfiguration,
    delivery_from_document,
    delivery_to_document,
    engine_from_document,
    engine_to_document,
    materialization_result_id,
    modeler_from_document,
    modeler_to_document,
)
from ada.alarms.persistence.errors import AlarmMaterializationPersistenceError
from atlanticus.state import AtomicJsonStore, StateError


@dataclass(frozen=True, slots=True)
# Representa cualquier versión durable ya inspeccionada.
class AlarmMaterializationVersion:
    manifest: AlarmMaterializationManifest
    manifest_sha256: str
    engine: EngineAlarmConfiguration | None
    modeler: ModelerAlarmConfiguration | None
    delivery: DeliveryAlarmConfiguration | None


@dataclass(frozen=True, slots=True)
# Vista tipada de una versión READY con los tres contratos cargados.
class ReadyAlarmMaterialization:
    result_id: str
    manifest: AlarmMaterializationManifest
    manifest_sha256: str
    engine: EngineAlarmConfiguration
    modeler: ModelerAlarmConfiguration
    delivery: DeliveryAlarmConfiguration


@dataclass(frozen=True, slots=True)
# Resultado de una publicación e indicador de promoción del head READY.
class AlarmMaterializationPublicationResult:
    result_id: str
    status: AlarmResolutionStatus
    manifest_sha256: str
    promoted_ready: bool


# Ubicación durable propia de ada-alarm-engine dentro del volumen compartido.
def materialization_root(volume_path: Path) -> Path:
    if not isinstance(volume_path, Path) or not volume_path.is_absolute():
        raise ValueError('VOLUMEN_PATH must be an absolute Path')
    return volume_path / 'ada-alarm-engine' / 'alarms' / 'materialization'


# Store local que publica por staging, valida y promueve atómicamente el head READY.
class LocalAlarmMaterializationStore:
    def __init__(self, *, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError('Materialization root must be an absolute Path')
        self._root = root
        self._versions = root / 'versions'
        self._heads = AtomicJsonStore(root_path=root, max_document_bytes=None)

    # Publica idempotentemente; un BLOCKED nunca reemplaza el último READY.
    def publish(
        self,
        *,
        source_key: str,
        provenance: AlarmMaterializationProvenance,
        resolution: AlarmConfigurationResolution,
    ) -> AlarmMaterializationPublicationResult:
        if not isinstance(provenance, AlarmMaterializationProvenance):
            raise TypeError('provenance must be an AlarmMaterializationProvenance')
        if not isinstance(resolution, AlarmConfigurationResolution):
            raise TypeError('resolution must be an AlarmConfigurationResolution')
        self._validate_resolution_provenance(provenance, resolution)
        result_id = materialization_result_id(
            source_key=source_key,
            projection_digest=provenance.projection_digest,
            qualification_digest=provenance.qualification_digest,
        )
        existing = self.read_result(source_key=source_key, result_id=result_id)
        if existing is not None:
            self._validate_existing(existing, provenance, resolution)
            promoted = False
            if resolution.status is AlarmResolutionStatus.READY:
                promoted = self._promote_ready(existing.manifest, existing.manifest_sha256)
            return AlarmMaterializationPublicationResult(
                result_id=result_id,
                status=resolution.status,
                manifest_sha256=existing.manifest_sha256,
                promoted_ready=promoted,
            )
        version = self._create_version(
            source_key=source_key,
            result_id=result_id,
            provenance=provenance,
            resolution=resolution,
        )
        promoted = False
        if resolution.status is AlarmResolutionStatus.READY:
            promoted = self._promote_ready(version.manifest, version.manifest_sha256)
        return AlarmMaterializationPublicationResult(
            result_id=result_id,
            status=resolution.status,
            manifest_sha256=version.manifest_sha256,
            promoted_ready=promoted,
        )

    # Lee una versión exacta y verifica manifest, inventario y hashes.
    def read_result(
        self,
        *,
        source_key: str,
        result_id: str,
    ) -> AlarmMaterializationVersion | None:
        path = self._version_path(result_id)
        if not path.exists() and not path.is_symlink():
            return None
        return self._inspect_version(path, source_key=source_key, result_id=result_id)

    def read_ready(
        self,
        *,
        source_key: str,
        result_id: str,
        expected_manifest_sha256: str | None = None,
    ) -> ReadyAlarmMaterialization:
        version = self.read_result(source_key=source_key, result_id=result_id)
        if version is None or version.manifest.status is not AlarmResolutionStatus.READY:
            raise AlarmMaterializationPersistenceError('READY materialization is unavailable')
        if (
            expected_manifest_sha256 is not None
            and version.manifest_sha256 != expected_manifest_sha256
        ):
            raise AlarmMaterializationPersistenceError('READY manifest integrity check failed')
        if version.engine is None or version.modeler is None or version.delivery is None:
            raise AlarmMaterializationPersistenceError(
                'READY materialization artifacts are missing'
            )
        return ReadyAlarmMaterialization(
            result_id=result_id,
            manifest=version.manifest,
            manifest_sha256=version.manifest_sha256,
            engine=version.engine,
            modeler=version.modeler,
            delivery=version.delivery,
        )

    # Resuelve ready.json y vuelve a comprobar integridad antes de entregar datos.
    def read_published_ready(self, *, source_key: str) -> ReadyAlarmMaterialization | None:
        pointer = self._read_ready_pointer(source_key=source_key)
        if pointer is None:
            return None
        ready = self.read_ready(
            source_key=source_key,
            result_id=pointer.result_id,
            expected_manifest_sha256=pointer.manifest_sha256,
        )
        if ready.manifest.resolution_key != pointer.resolution_key:
            raise AlarmMaterializationPersistenceError('READY pointer resolution key mismatch')
        return ready

    # Construye una versión completa en staging antes del rename atómico.
    def _create_version(
        self,
        *,
        source_key: str,
        result_id: str,
        provenance: AlarmMaterializationProvenance,
        resolution: AlarmConfigurationResolution,
    ) -> AlarmMaterializationVersion:
        stage: Path | None = None
        try:
            self._versions.mkdir(parents=True, exist_ok=True)
            self._remove_orphan_stages(result_id)
            stage = self._versions / f'.{result_id}.{uuid4().hex}.staging'
            stage.mkdir(exist_ok=False)
            writer = AtomicJsonStore(root_path=stage, max_document_bytes=None)
            artifacts: dict[str, AlarmMaterializationArtifact] = {}
            if resolution.status is AlarmResolutionStatus.READY:
                documents = self._ready_documents(resolution)
                for label in ('engine', 'modeler', 'delivery'):
                    filename = f'{label}.json'
                    writer.replace(filename, documents[label])
                    payload = (stage / filename).read_bytes()
                    artifacts[label] = AlarmMaterializationArtifact(
                        path=filename,
                        size_bytes=len(payload),
                        sha256=sha256(payload).hexdigest(),
                    )
            manifest = AlarmMaterializationManifest(
                source_key=source_key,
                result_id=result_id,
                status=resolution.status,
                resolution_key=resolution.resolution_key,
                provenance=provenance,
                findings=resolution.findings,
                artifacts=artifacts,
            )
            writer.replace('manifest.json', manifest.to_document())
            inspected = self._inspect_version(stage, source_key=source_key, result_id=result_id)
            _fsync_directory(stage)
            os.rename(stage, self._version_path(result_id))
            stage = None
            _fsync_directory(self._versions)
            return inspected
        except (OSError, StateError, TypeError, ValueError) as error:
            raise AlarmMaterializationPersistenceError(
                'Could not publish local Alarm materialization version'
            ) from error
        finally:
            if stage is not None:
                shutil.rmtree(stage, ignore_errors=True)

    def _inspect_version(
        self,
        path: Path,
        *,
        source_key: str,
        result_id: str,
    ) -> AlarmMaterializationVersion:
        if not path.is_dir() or path.is_symlink():
            raise AlarmMaterializationPersistenceError('Invalid materialization version directory')
        manifest_document, manifest_digest, _ = self._read_document(path / 'manifest.json')
        try:
            manifest = AlarmMaterializationManifest.from_document(manifest_document)
        except (KeyError, TypeError, ValueError) as error:
            raise AlarmMaterializationPersistenceError(
                'Invalid materialization manifest'
            ) from error
        if manifest.source_key != source_key or manifest.result_id != result_id:
            raise AlarmMaterializationPersistenceError('Invalid materialization manifest identity')
        expected_files = {'manifest.json'}
        if manifest.status is AlarmResolutionStatus.BLOCKED:
            self._require_exact_files(path, expected_files)
            return AlarmMaterializationVersion(
                manifest=manifest,
                manifest_sha256=manifest_digest,
                engine=None,
                modeler=None,
                delivery=None,
            )
        expected_files.update({'engine.json', 'modeler.json', 'delivery.json'})
        self._require_exact_files(path, expected_files)
        documents: dict[str, dict[str, object]] = {}
        for label in ('engine', 'modeler', 'delivery'):
            artifact = manifest.artifacts[label]
            document, digest, size = self._read_document(path / artifact.path)
            if digest != artifact.sha256 or size != artifact.size_bytes:
                raise AlarmMaterializationPersistenceError(
                    'READY materialization integrity check failed'
                )
            documents[label] = document
        try:
            engine = engine_from_document(documents['engine'])
            modeler = modeler_from_document(documents['modeler'])
            delivery = delivery_from_document(documents['delivery'])
        except (KeyError, TypeError, ValueError) as error:
            raise AlarmMaterializationPersistenceError(
                'READY materialization artifact contract is invalid'
            ) from error
        if (
            engine.resolution_key != manifest.resolution_key
            or modeler.resolution_key != manifest.resolution_key
            or delivery.resolution_key != manifest.resolution_key
        ):
            raise AlarmMaterializationPersistenceError(
                'READY materialization resolution key mismatch'
            )
        return AlarmMaterializationVersion(
            manifest=manifest,
            manifest_sha256=manifest_digest,
            engine=engine,
            modeler=modeler,
            delivery=delivery,
        )

    # Cambia el head sólo después de tener una versión READY válida y durable.
    def _promote_ready(
        self,
        manifest: AlarmMaterializationManifest,
        manifest_sha256: str,
    ) -> bool:
        if manifest.status is not AlarmResolutionStatus.READY:
            raise AlarmMaterializationPersistenceError('Only READY materialization can be promoted')
        pointer = AlarmMaterializationReadyPointer(
            source_key=manifest.source_key,
            result_id=manifest.result_id,
            resolution_key=manifest.resolution_key,
            manifest_sha256=manifest_sha256,
        )
        current = self._read_ready_pointer(source_key=manifest.source_key)
        if current == pointer:
            return False
        try:
            self._heads.replace('ready.json', pointer.to_document())
        except StateError as error:
            raise AlarmMaterializationPersistenceError(
                'Could not promote local READY materialization'
            ) from error
        return True

    def _read_ready_pointer(
        self,
        *,
        source_key: str,
    ) -> AlarmMaterializationReadyPointer | None:
        if (self._root / 'ready.json').is_symlink():
            raise AlarmMaterializationPersistenceError('READY pointer must not be a link')
        try:
            document = self._heads.read('ready.json')
        except StateError as error:
            raise AlarmMaterializationPersistenceError(
                'Could not read local READY pointer'
            ) from error
        if document is None:
            return None
        try:
            pointer = AlarmMaterializationReadyPointer.from_document(document)
        except (KeyError, TypeError, ValueError) as error:
            raise AlarmMaterializationPersistenceError('Invalid local READY pointer') from error
        if pointer.source_key != source_key:
            raise AlarmMaterializationPersistenceError('READY pointer source key mismatch')
        return pointer

    def _validate_resolution_provenance(
        self,
        provenance: AlarmMaterializationProvenance,
        resolution: AlarmConfigurationResolution,
    ) -> None:
        if (
            resolution.resolution_key.alarm_configuration_revision
            != provenance.source_release_id
            or resolution.resolution_key.confirmed_tool_catalog_revision
            != provenance.confirmed_tool_catalog_revision
        ):
            raise AlarmMaterializationPersistenceError(
                'Resolution key does not match materialization provenance'
            )

    def _validate_existing(
        self,
        version: AlarmMaterializationVersion,
        provenance: AlarmMaterializationProvenance,
        resolution: AlarmConfigurationResolution,
    ) -> None:
        manifest = version.manifest
        if (
            manifest.status is not resolution.status
            or manifest.resolution_key != resolution.resolution_key
            or manifest.provenance != provenance
            or manifest.findings != resolution.findings
        ):
            raise AlarmMaterializationPersistenceError(
                'Materialization result identity conflicts with existing content'
            )
        if resolution.status is AlarmResolutionStatus.BLOCKED:
            return
        if version.engine is None or version.modeler is None or version.delivery is None:
            raise AlarmMaterializationPersistenceError('Existing READY artifacts are missing')
        if (
            version.engine != resolution.engine_configuration
            or version.modeler != resolution.modeler_configuration
            or version.delivery != resolution.delivery_configuration
        ):
            raise AlarmMaterializationPersistenceError(
                'Materialization result identity conflicts with existing artifacts'
            )

    @staticmethod
    def _ready_documents(
        resolution: AlarmConfigurationResolution,
    ) -> dict[str, dict[str, object]]:
        if (
            resolution.engine_configuration is None
            or resolution.modeler_configuration is None
            or resolution.delivery_configuration is None
        ):
            raise AlarmMaterializationPersistenceError(
                'READY resolution requires Engine, Modeler, and Delivery configurations'
            )
        return {
            'engine': engine_to_document(resolution.engine_configuration),
            'modeler': modeler_to_document(resolution.modeler_configuration),
            'delivery': delivery_to_document(resolution.delivery_configuration),
        }

    @staticmethod
    def _require_exact_files(path: Path, expected: set[str]) -> None:
        try:
            entries = {entry.name for entry in path.iterdir()}
        except OSError as error:
            raise AlarmMaterializationPersistenceError(
                'Could not inspect materialization version directory'
            ) from error
        if entries != expected:
            raise AlarmMaterializationPersistenceError(
                'Materialization version contains an invalid file inventory'
            )

    @staticmethod
    def _read_document(path: Path) -> tuple[dict[str, object], str, int]:
        try:
            if path.is_symlink():
                raise AlarmMaterializationPersistenceError(
                    'Materialization artifact must not be a link'
                )
            payload = path.read_bytes()
            document = json.loads(payload)
        except AlarmMaterializationPersistenceError:
            raise
        except (OSError, UnicodeError, ValueError) as error:
            raise AlarmMaterializationPersistenceError(
                'Could not read local materialization artifact'
            ) from error
        if not isinstance(document, dict):
            raise AlarmMaterializationPersistenceError('Materialization artifact must be an object')
        return document, sha256(payload).hexdigest(), len(payload)

    def _version_path(self, result_id: str) -> Path:
        if not isinstance(result_id, str) or not result_id.startswith('alarm-materialization-'):
            raise AlarmMaterializationPersistenceError('Invalid materialization result identity')
        expected = 64 + len('alarm-materialization-')
        if len(result_id) != expected or any(
            character not in '0123456789abcdef'
            for character in result_id[len('alarm-materialization-') :]
        ):
            raise AlarmMaterializationPersistenceError('Invalid materialization result identity')
        return self._versions / result_id

    def _remove_orphan_stages(self, result_id: str) -> None:
        for stage in self._versions.glob(f'.{result_id}.*.staging'):
            if stage.is_symlink() or not stage.is_dir():
                raise AlarmMaterializationPersistenceError('Invalid orphan staging directory')
            try:
                shutil.rmtree(stage)
            except OSError as error:
                raise AlarmMaterializationPersistenceError(
                    'Could not remove orphan materialization staging directory'
                ) from error


def _fsync_directory(path: Path) -> None:
    if os.name == 'nt':
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
