# Espejo pedagógico en español del archivo productivo equivalente.
# Mantiene exactamente el mismo comportamiento; los comentarios explican la intención.
# Este incremento prioriza el flujo vertical Runtime -> Modeler -> Delivery -> Cosmos.

from __future__ import annotations

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
from ada_command_center.processes.alarms_modeler.projection import (
    AlarmProjectionError,
    build_projection_index,
    build_projection_snapshots,
    document_digest,
    projection_path,
)
from atlanticus.state import AtomicJsonStore

_CURRENT_PATH = 'current/latest.json'
_INDEX_PATH = 'current/index.json'


class AlarmModelerInputError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AlarmModelerCycleResult:
    status: str
    projected_tools: int = 0


@dataclass(slots=True)
class LocalAlarmModeler:
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
    def runtime_root(self) -> Path:
        return self.volume_path / 'ada-command-center' / 'alarms' / 'runtime' / 'output'

    @property
    def output_root(self) -> Path:
        return self.volume_path / 'ada-command-center' / 'alarms' / 'modeler' / 'output'

    @property
    def alarms_root(self) -> Path:
        return self.volume_path / 'ada-command-center' / 'alarms'

    def recover(self, _context: object) -> None:
        store = AtomicJsonStore(root_path=self.output_root, max_document_bytes=None)
        index = store.read(_INDEX_PATH)
        if index is None:
            return
        self._validate_index(index, store)

    def model(self, context: object) -> AlarmModelerCycleResult:
        head = self._effective()
        if head is None:
            return AlarmModelerCycleResult(status='WAITING_EFFECTIVE')
        current = AtomicJsonStore(
            root_path=self.runtime_root, max_document_bytes=None
        ).read(_CURRENT_PATH)
        if current is None:
            return AlarmModelerCycleResult(status='WAITING_CURRENT')
        try:
            pin = AlarmArtifactRefSnapshot.from_document(current['artifact_ref'])
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            raise AlarmModelerInputError('Runtime current artifact reference is invalid') from error
        if pin != head.target_artifact_ref:
            return AlarmModelerCycleResult(status='WAITING_CURRENT')
        try:
            ready = LocalAlarmMaterializationReader(
                root=materialization_root(self.volume_path)
            ).read_exact_ready(
                source_key=pin.source_key,
                result_id=pin.result_id,
                manifest_sha256=pin.manifest_sha256,
            )
            snapshots = build_projection_snapshots(
                current_document=current,
                runtime_configuration=ready.runtime,
                delivery_configuration=ready.delivery,
            )
        except (TypeError, ValueError, OSError, RuntimeError, AlarmProjectionError) as error:
            raise AlarmModelerInputError('Alarm projection could not be built') from error
        if self._effective() != head:
            return AlarmModelerCycleResult(status='EFFECTIVE_CHANGED')
        index = build_projection_index(
            artifact_ref=current['artifact_ref'],
            snapshot_timestamp=current['state']['as_of'],
            snapshots=snapshots,
        )
        store = AtomicJsonStore(root_path=self.output_root, max_document_bytes=None)
        previous = store.read(_INDEX_PATH)
        if previous is not None:
            self._validate_index(previous, store)
            old_at = previous['snapshot_timestamp']
            new_at = index['snapshot_timestamp']
            if old_at > new_at:
                return AlarmModelerCycleResult(status='STALE_SOURCE')
            if old_at == new_at:
                if previous != index:
                    raise AlarmModelerInputError(
                        'Different projections share snapshot_timestamp'
                    )
                return AlarmModelerCycleResult(
                    status='CURRENT_UNCHANGED',
                    projected_tools=len(snapshots),
                )
        context.assert_lease_current()
        with context.fenced_mutation():
            if self._effective() != head:
                return AlarmModelerCycleResult(status='EFFECTIVE_CHANGED')
            for snapshot in snapshots:
                store.replace(projection_path(snapshot['tool_key']), snapshot)
            store.replace(_INDEX_PATH, index)
        return AlarmModelerCycleResult(
            status='CURRENT_MODELED',
            projected_tools=len(snapshots),
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
            raise AlarmModelerInputError('Engine EFFECTIVE head projection is invalid') from error
        if head.target_artifact_ref.source_key != self.source_key:
            raise AlarmModelerInputError('Engine EFFECTIVE source differs from Modeler source')
        return head

    @staticmethod
    def _validate_index(index: dict[str, object], store: AtomicJsonStore) -> None:
        required = {
            'document_type',
            'schema_version',
            'artifact_ref',
            'snapshot_timestamp',
            'snapshots',
            'sha256',
        }
        if (
            not isinstance(index, dict)
            or set(index) != required
            or index.get('document_type') != 'ada_alarm_modeler_projection_index'
            or index.get('schema_version') != 1
        ):
            raise AlarmModelerInputError('Existing Modeler projection index is invalid')
        expected = index['sha256']
        payload = {key: value for key, value in index.items() if key != 'sha256'}
        if not isinstance(expected, str) or document_digest(payload) != expected:
            raise AlarmModelerInputError('Existing Modeler projection index checksum mismatch')
        if not isinstance(index['snapshots'], list):
            raise AlarmModelerInputError('Existing Modeler projection inventory is invalid')
        for item in index['snapshots']:
            if not isinstance(item, dict) or set(item) != {'tool_key', 'path', 'sha256'}:
                raise AlarmModelerInputError('Existing Modeler projection inventory is invalid')
            snapshot = store.read(item['path'])
            if snapshot is None or snapshot.get('sha256') != item['sha256']:
                raise AlarmModelerInputError('Existing Modeler projection snapshot is unavailable')
            snapshot_payload = {
                key: value for key, value in snapshot.items() if key != 'sha256'
            }
            if document_digest(snapshot_payload) != item['sha256']:
                raise AlarmModelerInputError('Existing Modeler projection checksum mismatch')
