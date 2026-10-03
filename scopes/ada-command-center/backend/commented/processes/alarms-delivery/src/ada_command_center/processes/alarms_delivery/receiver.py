# Espejo pedagógico en español del archivo productivo equivalente.
# Mantiene exactamente el mismo comportamiento; los comentarios explican la intención.
# Este incremento prioriza el flujo vertical Runtime -> Modeler -> Delivery -> Cosmos.

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ada_command_center.alarms.materialization.local_reader import (
    LocalAlarmMaterializationReader,
    materialization_root,
)
from ada_command_center.alarms.persistence import (
    AlarmArtifactRefSnapshot,
    AlarmEffectiveConfigurationHead,
)
from atlanticus.state import AtomicJsonStore

_INDEX_PATH = 'current/index.json'


class AlarmDeliveryInputError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DeliveryProjectionSnapshot:
    tool_key: str
    document: dict[str, object]


@dataclass(frozen=True, slots=True)
class DeliveryInputCycleResult:
    current_status: str
    snapshots: tuple[DeliveryProjectionSnapshot, ...] = ()


@dataclass(slots=True)
class LocalAlarmDeliveryReceiver:
    volume_path: Path
    source_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.volume_path, Path) or not self.volume_path.is_absolute():
            raise ValueError('VOLUMEN_PATH must be an absolute Path')
        if (
            not isinstance(self.source_key, str)
            or not self.source_key
            or self.source_key != self.source_key.strip()
        ):
            raise ValueError('ALARM_CONFIGURATION_SOURCE_KEY must be non-empty text')

    @property
    def modeler_root(self) -> Path:
        return self.volume_path / 'ada-command-center' / 'alarms' / 'modeler' / 'output'

    @property
    def alarms_root(self) -> Path:
        return self.volume_path / 'ada-command-center' / 'alarms'

    def recover(self, _context: object) -> None:
        index = AtomicJsonStore(root_path=self.modeler_root, max_document_bytes=None).read(
            _INDEX_PATH
        )
        if index is not None:
            self._read_projection(index)

    def consume(self, context: object) -> DeliveryInputCycleResult:
        context.assert_lease_current()
        head = self._effective()
        if head is None:
            return DeliveryInputCycleResult(current_status='WAITING_EFFECTIVE')
        store = AtomicJsonStore(root_path=self.modeler_root, max_document_bytes=None)
        index = store.read(_INDEX_PATH)
        if index is None:
            return DeliveryInputCycleResult(current_status='WAITING_MODELER')
        pin, snapshots = self._read_projection(index)
        if pin != head.target_artifact_ref:
            return DeliveryInputCycleResult(current_status='WAITING_MODELER')
        self._exact(pin)
        if self._effective() != head:
            return DeliveryInputCycleResult(current_status='EFFECTIVE_CHANGED')
        return DeliveryInputCycleResult(
            current_status='CURRENT_AVAILABLE',
            snapshots=snapshots,
        )

    def _effective(self) -> AlarmEffectiveConfigurationHead | None:
        document = AtomicJsonStore(
            root_path=self.alarms_root, max_document_bytes=None
        ).read('runtime/state/effective-head.json')
        if document is None:
            return None
        try:
            head = AlarmEffectiveConfigurationHead.from_document(document)
        except (TypeError, ValueError, RuntimeError) as error:
            raise AlarmDeliveryInputError('Engine EFFECTIVE head projection is invalid') from error
        if head.target_artifact_ref.source_key != self.source_key:
            raise AlarmDeliveryInputError('Engine EFFECTIVE source differs from Delivery source')
        return head

    def _exact(self, pin: AlarmArtifactRefSnapshot) -> None:
        try:
            result = LocalAlarmMaterializationReader(
                root=materialization_root(self.volume_path)
            ).read_exact_ready(
                source_key=pin.source_key,
                result_id=pin.result_id,
                manifest_sha256=pin.manifest_sha256,
            )
        except (TypeError, ValueError, OSError, RuntimeError) as error:
            raise AlarmDeliveryInputError('Exact alarm configuration is unavailable') from error
        expected = pin.as_document()['resolution_key']
        if (
            result.result_id != pin.result_id
            or result.manifest_sha256 != pin.manifest_sha256
            or {
                'alarm_configuration_revision': result.runtime.resolution_key.alarm_configuration_revision,
                'confirmed_tool_catalog_revision': (
                    result.runtime.resolution_key.confirmed_tool_catalog_revision
                ),
            }
            != expected
        ):
            raise AlarmDeliveryInputError('Delivery configuration does not match artifact')

    def _read_projection(
        self, index: dict[str, object]
    ) -> tuple[AlarmArtifactRefSnapshot, tuple[DeliveryProjectionSnapshot, ...]]:
        if (
            not isinstance(index, dict)
            or set(index)
            != {
                'document_type',
                'schema_version',
                'artifact_ref',
                'snapshot_timestamp',
                'snapshots',
                'sha256',
            }
            or index.get('document_type') != 'ada_alarm_modeler_projection_index'
            or index.get('schema_version') != 1
        ):
            raise AlarmDeliveryInputError('Modeler projection index is invalid')
        _verify_digest(index)
        try:
            pin = AlarmArtifactRefSnapshot.from_document(index['artifact_ref'])
        except (TypeError, ValueError, RuntimeError) as error:
            raise AlarmDeliveryInputError('Modeler artifact reference is invalid') from error
        if pin.source_key != self.source_key:
            raise AlarmDeliveryInputError('Modeler source differs from Delivery source')
        inventory = index['snapshots']
        if not isinstance(inventory, list):
            raise AlarmDeliveryInputError('Modeler projection inventory is invalid')
        store = AtomicJsonStore(root_path=self.modeler_root, max_document_bytes=None)
        snapshots = []
        seen = set()
        for item in inventory:
            if not isinstance(item, dict) or set(item) != {'tool_key', 'path', 'sha256'}:
                raise AlarmDeliveryInputError('Modeler projection inventory is invalid')
            tool_key = item['tool_key']
            if not isinstance(tool_key, str) or not tool_key or tool_key in seen:
                raise AlarmDeliveryInputError('Modeler projection tool inventory is invalid')
            seen.add(tool_key)
            document = store.read(item['path'])
            if document is None:
                raise AlarmDeliveryInputError('Modeler projection snapshot is unavailable')
            _verify_digest(document)
            if (
                document.get('document_type') != 'ada_alarm_projection_snapshot'
                or document.get('schema_version') != 1
                or document.get('tool_key') != tool_key
                or document.get('artifact_ref') != index['artifact_ref']
                or document.get('snapshot_timestamp') != index['snapshot_timestamp']
                or document.get('sha256') != item['sha256']
            ):
                raise AlarmDeliveryInputError('Modeler projection snapshot does not match index')
            snapshots.append(DeliveryProjectionSnapshot(tool_key=tool_key, document=document))
        return pin, tuple(snapshots)


def _verify_digest(document: Mapping[str, object]) -> None:
    digest = document.get('sha256')
    if not isinstance(digest, str) or len(digest) != 64:
        raise AlarmDeliveryInputError('Projection checksum is missing or invalid')
    payload = {key: value for key, value in document.items() if key != 'sha256'}
    actual = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode(
            'utf-8'
        )
    ).hexdigest()
    if actual != digest:
        raise AlarmDeliveryInputError('Projection checksum mismatch')
