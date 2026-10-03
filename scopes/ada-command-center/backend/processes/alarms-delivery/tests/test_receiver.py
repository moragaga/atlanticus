from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from types import SimpleNamespace

from ada_command_center.alarms.persistence import (
    AlarmArtifactRefSnapshot,
    AlarmEffectiveConfigurationHead,
    JournalPosition,
)
from ada_command_center.processes.alarms_delivery import (
    LocalAlarmDeliveryReceiver,
    receiver as receiver_module,
)
from atlanticus.state import AtomicJsonStore

_SOURCE = 'alarm-configuration'
_AT = '2026-10-03T14:37:01Z'


class _Lease:
    def assert_lease_current(self):
        return None

    @contextmanager
    def fenced_mutation(self):
        yield


def _digest(document):
    return hashlib.sha256(
        json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    ).hexdigest()


def _pin():
    return AlarmArtifactRefSnapshot(
        source_key=_SOURCE,
        result_id='alarm-materialization-' + 'a' * 64,
        manifest_sha256='b' * 64,
        alarm_configuration_revision='R1',
        confirmed_tool_catalog_revision='T1',
    )


def _head(volume, pin):
    store = AtomicJsonStore(root_path=volume / 'ada-command-center' / 'alarms')
    store.replace(
        'runtime/state/effective-head.json',
        AlarmEffectiveConfigurationHead(
            adoption_id='adoption-1',
            adoption_record_hash='sha256:' + '9' * 64,
            adoption_position=JournalPosition(
                segment_id='2026-10-03T14Z#0000',
                byte_offset=1,
                commit_id='adoption-1',
            ),
            target_artifact_ref=pin,
            effective_at=_AT,
        ).as_document(),
    )


def _projection(volume, pin):
    snapshot = {
        'id': 'alarm_projection_snapshot:1234',
        'document_type': 'ada_alarm_projection_snapshot',
        'schema_version': 1,
        'artifact_ref': pin.as_document(),
        'snapshot_timestamp': _AT,
        'tool_key': 'tool-a',
        'alarms': {},
        'operator_pool': [],
        'operator_view': [],
        'meta': {
            'operator_count': 0,
            'operator_pool_count': 0,
            'total_count': 0,
            'max_visible_slots': 6,
        },
    }
    snapshot['sha256'] = _digest(snapshot)
    path = 'current/tools/1234/latest.json'
    index = {
        'document_type': 'ada_alarm_modeler_projection_index',
        'schema_version': 1,
        'artifact_ref': pin.as_document(),
        'snapshot_timestamp': _AT,
        'snapshots': [
            {'tool_key': 'tool-a', 'path': path, 'sha256': snapshot['sha256']}
        ],
    }
    index['sha256'] = _digest(index)
    store = AtomicJsonStore(
        root_path=volume / 'ada-command-center' / 'alarms' / 'modeler' / 'output',
        max_document_bytes=None,
    )
    store.replace(path, snapshot)
    store.replace('current/index.json', index)


def test_delivery_reads_exact_modeler_projection(monkeypatch, tmp_path):
    pin = _pin()
    _head(tmp_path, pin)
    _projection(tmp_path, pin)

    class _Reader:
        def __init__(self, *, root):
            pass

        def read_exact_ready(self, **kwargs):
            key = SimpleNamespace(
                alarm_configuration_revision='R1',
                confirmed_tool_catalog_revision='T1',
            )
            return SimpleNamespace(
                result_id=pin.result_id,
                manifest_sha256=pin.manifest_sha256,
                runtime=SimpleNamespace(resolution_key=key),
            )

    monkeypatch.setattr(receiver_module, 'LocalAlarmMaterializationReader', _Reader)
    receiver = LocalAlarmDeliveryReceiver(tmp_path, _SOURCE)
    result = receiver.consume(_Lease())
    assert result.current_status == 'CURRENT_AVAILABLE'
    assert len(result.snapshots) == 1
    assert result.snapshots[0].tool_key == 'tool-a'
    assert result.snapshots[0].document['id'] == 'alarm_projection_snapshot:1234'
