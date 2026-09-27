from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from ada_command_center.alarms.materialization.codec import (
    delivery_from_document,
    runtime_from_document,
)
from ada_command_center.alarms.materialization.delivery import DeliveryAlarmConfiguration
from ada_command_center.alarms.materialization.runtime import RuntimeAlarmConfiguration

DOCUMENT_TYPE = 'ada_command_center_alarm_materialization_result'
SCHEMA_VERSION = 1
READY_DOCUMENT_TYPE = 'ada_command_center_alarm_materialization_ready'
_RESULT_PATTERN = re.compile(r'alarm-materialization-[0-9a-f]{64}')
_SHA256_PATTERN = re.compile(r'[0-9a-f]{64}')


class AlarmMaterializationPublicationError(RuntimeError):
    pass


def materialization_root(volume_path: Path) -> Path:
    if not isinstance(volume_path, Path) or not volume_path.is_absolute():
        raise ValueError('VOLUMEN_PATH must be an absolute Path')
    return volume_path / 'ada-command-center' / 'alarms' / 'materialization'


def _encode(document: object) -> bytes:
    return json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode(
        'utf-8'
    )


def _digest(document: object) -> str:
    return sha256(_encode(document)).hexdigest()


def materialization_result_id(
    *, source_key: str, projection_digest: str, qualification_digest: str
) -> str:
    return 'alarm-materialization-' + _digest(
        {
            'source_key': source_key,
            'projection_digest': projection_digest,
            'qualification_digest': qualification_digest,
        }
    )


def _require_result_id(value: object) -> str:
    if not isinstance(value, str) or _RESULT_PATTERN.fullmatch(value) is None:
        raise AlarmMaterializationPublicationError('Invalid materialization result identity')
    return value


def _require_sha256(value: object) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise AlarmMaterializationPublicationError('Invalid materialization digest')
    return value


@dataclass(frozen=True, slots=True)
class ReadyAlarmMaterialization:
    result_id: str
    runtime: RuntimeAlarmConfiguration
    delivery: DeliveryAlarmConfiguration
    manifest: dict[str, object]
    manifest_sha256: str


class LocalAlarmMaterializationReader:
    def __init__(self, *, root: Path) -> None:
        if not isinstance(root, Path) or not root.is_absolute():
            raise ValueError('Materialization root must be an absolute Path')
        self._root = root
        self._versions = root / 'versions'

    def read_exact_ready(
        self, *, source_key: str, result_id: str, manifest_sha256: str
    ) -> ReadyAlarmMaterialization:
        return self.read_ready(
            source_key=source_key,
            result_id=result_id,
            expected_manifest_sha256=_require_sha256(manifest_sha256),
        )

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
            raise AlarmMaterializationPublicationError(
                'READY materialization artifacts are missing'
            )
        return ReadyAlarmMaterialization(
            result_id=result_id,
            runtime=runtime,
            delivery=delivery,
            manifest=manifest,
            manifest_sha256=digest,
        )

    def _read_head(self, *, source_key: str) -> dict[str, object] | None:
        head_path = self._root / 'ready.json'
        if not head_path.exists() and not head_path.is_symlink():
            return None
        try:
            head, _ = self._read_document(head_path)
        except AlarmMaterializationPublicationError as error:
            raise AlarmMaterializationPublicationError(
                'Could not read local READY pointer'
            ) from error
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

    def _read_version(
        self, *, source_key: str, result_id: str
    ) -> (
        tuple[
            dict[str, object],
            RuntimeAlarmConfiguration | None,
            DeliveryAlarmConfiguration | None,
            str,
        ]
        | None
    ):
        path = self._version_path(result_id)
        if not path.exists() and not path.is_symlink():
            return None
        return self._inspect_version(path, source_key=source_key, result_id=result_id)

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
            != materialization_result_id(
                source_key=source_key,
                projection_digest=provenance.get('projection_digest'),
                qualification_digest=provenance.get('qualification_digest'),
            )
        ):
            raise AlarmMaterializationPublicationError('Invalid materialization manifest identity')
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
            raise AlarmMaterializationPublicationError(
                'Invalid materialization provenance timestamps'
            )
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
            if artifacts or any(
                (path / f'{name}.json').exists() for name in ('runtime', 'delivery')
            ):
                raise AlarmMaterializationPublicationError(
                    'BLOCKED result contains executable artifacts'
                )
            if not any(
                isinstance(item, dict) and item.get('severity') == 'BLOCKING'
                for item in manifest['findings']
            ):
                raise AlarmMaterializationPublicationError(
                    'BLOCKED materialization findings are invalid'
                )
            return manifest, None, None, digest
        if set(artifacts) != {'runtime', 'delivery'}:
            raise AlarmMaterializationPublicationError(
                'READY materialization artifacts are missing'
            )
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
                raise AlarmMaterializationPublicationError(
                    'Invalid materialization artifact inventory'
                )
            expected_digest = _require_sha256(description.get('sha256'))
            documents[label], actual_digest, size = self._read_document_with_size(
                path / f'{label}.json'
            )
            if actual_digest != expected_digest or size != description['size_bytes']:
                raise AlarmMaterializationPublicationError(
                    'READY materialization integrity check failed'
                )
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
            raise AlarmMaterializationPublicationError(
                'READY materialization resolution key mismatch'
            )
        return manifest, runtime, delivery, digest

    @staticmethod
    def _read_document(path: Path) -> tuple[dict[str, object], str]:
        document, digest, _ = LocalAlarmMaterializationReader._read_document_with_size(path)
        return document, digest

    @staticmethod
    def _read_document_with_size(path: Path) -> tuple[dict[str, object], str, int]:
        try:
            if path.is_symlink():
                raise AlarmMaterializationPublicationError(
                    'Materialization artifact must not be a link'
                )
            payload = path.read_bytes()
            document = json.loads(payload)
        except (OSError, UnicodeError, ValueError) as error:
            raise AlarmMaterializationPublicationError(
                'Could not read local materialization artifact'
            ) from error
        if not isinstance(document, dict):
            raise AlarmMaterializationPublicationError('Materialization artifact must be an object')
        return document, sha256(payload).hexdigest(), len(payload)

    def _version_path(self, result_id: str) -> Path:
        return self._versions / _require_result_id(result_id)
