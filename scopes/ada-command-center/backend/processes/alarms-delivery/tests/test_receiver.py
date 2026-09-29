from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest

from ada_command_center.alarms.persistence import (
    AlarmArtifactRefSnapshot,
    AlarmEffectiveConfigurationHead,
    JournalPosition,
)
from ada_command_center.processes.alarms_delivery import (
    AlarmDeliveryInputError,
    LocalAlarmDeliveryReceiver,
    receiver as receiver_module,
)
from atlanticus.state import AtomicJsonStore

_SOURCE = 'alarm-configuration'
_SEGMENT = '2026-09-28T14Z#0000'
_AT = '2026-09-28T14:00:00Z'


class _Lease:
    def __init__(self):
        self.writes = 0

    def assert_lease_current(self):
        return None

    @contextmanager
    def fenced_mutation(self):
        self.writes += 1
        yield


def _pin(key='a'):
    return AlarmArtifactRefSnapshot(
        source_key=_SOURCE,
        result_id='alarm-materialization-' + key * 64,
        manifest_sha256=key * 64,
        alarm_configuration_revision='R10',
        confirmed_tool_catalog_revision='C5',
    )


def _engine(volume):
    return AtomicJsonStore(
        root_path=volume / 'ada-command-center' / 'alarms' / 'runtime' / 'output',
        max_document_bytes=None,
    )


def _input(volume):
    return AtomicJsonStore(
        root_path=volume / 'ada-command-center' / 'alarms' / 'delivery' / 'input',
        max_document_bytes=None,
    )


def _head(volume, pin):
    store = AtomicJsonStore(root_path=volume / 'ada-command-center' / 'alarms')
    head = AlarmEffectiveConfigurationHead(
        adoption_id='adoption-1',
        adoption_record_hash='sha256:' + '9' * 64,
        adoption_position=JournalPosition(
            segment_id=_SEGMENT, byte_offset=1, commit_id='adoption-1'
        ),
        target_artifact_ref=pin,
        effective_at=_AT,
    )
    store.replace('runtime/state/effective-head.json', head.as_document())
    return head


def _current(pin, *, as_of=_AT, alarms=None):
    document = {
        'document_type': 'ada_command_center_engine_resolved_current_state',
        'schema_version': 1,
        'artifact_ref': pin.as_document(),
        'state': {
            'resolution_key': pin.as_document()['resolution_key'],
            'as_of': as_of,
            'alarms': [] if alarms is None else alarms,
        },
    }
    document['sha256'] = receiver_module._hash(document)
    return document


def _alarm(*, as_of=_AT, observed_value=82.0):
    return {
        'identity': 'mina/temperature',
        'occurrence_id': 'occ-temperature',
        'episode_id': 'episode-mine',
        'started_at': _AT,
        'evaluation': {
            'status': 'ACTIVE',
            'evaluated_at': as_of,
            'evidence': {
                'contract_key': 'threshold',
                'contract_version': 'v1',
                'payload': {'observed_value': observed_value},
            },
            'error': None,
        },
        'priority': {'disposition': 'PREDOMINANT', 'blockers': []},
        'technical_hold': None,
        'management_cycle': None,
        'management_effect': None,
        'deactivation_effect': None,
        'pending_deactivation_request': None,
        'assignments': [],
        'pending_assignments': [],
    }


@pytest.fixture
def setup_receiver(monkeypatch, tmp_path):
    allowed = {_pin().result_id: _pin()}

    class _Reader:
        def __init__(self, *, root):
            assert root == tmp_path / 'ada-command-center' / 'alarms' / 'materialization'

        def read_exact_ready(self, *, source_key, result_id, manifest_sha256):
            pin = allowed[result_id]
            assert source_key == pin.source_key
            assert manifest_sha256 == pin.manifest_sha256
            resolution = SimpleNamespace(
                alarm_configuration_revision=pin.alarm_configuration_revision,
                confirmed_tool_catalog_revision=pin.confirmed_tool_catalog_revision,
            )
            return SimpleNamespace(
                result_id=result_id,
                manifest_sha256=manifest_sha256,
                runtime=SimpleNamespace(resolution_key=resolution),
                delivery=SimpleNamespace(resolution_key=resolution),
            )

    monkeypatch.setattr(receiver_module, 'LocalAlarmMaterializationReader', _Reader)
    return tmp_path, allowed, LocalAlarmDeliveryReceiver(tmp_path, _SOURCE)


def test_absent_effective_does_not_invent_empty_current(setup_receiver):
    volume, allowed, receiver = setup_receiver
    pin = _pin()
    _engine(volume).replace('current/latest.json', _current(pin))
    result = receiver.consume(_Lease())
    assert result.current_status == 'WAITING_EFFECTIVE'
    assert _input(volume).read('current/latest.json') is None


def test_waits_for_current_when_effective_is_available(setup_receiver):
    volume, allowed, receiver = setup_receiver
    _head(volume, _pin())
    assert receiver.consume(_Lease()).current_status == 'WAITING_CURRENT'
    assert _input(volume).read('current/latest.json') is None


def test_accepts_exact_empty_current_then_latest_evidence(setup_receiver):
    volume, allowed, receiver = setup_receiver
    pin = _pin()
    _head(volume, pin)
    _engine(volume).replace('current/latest.json', _current(pin))
    assert receiver.consume(_Lease()).current_status == 'CURRENT_STAGED'
    assert receiver.consume(_Lease()).current_status == 'CURRENT_UNCHANGED'
    newer = _current(pin, as_of='2026-09-28T14:05:00Z', alarms=[
        _alarm(as_of='2026-09-28T14:05:00Z', observed_value=89.0)
    ])
    _engine(volume).replace('current/latest.json', newer)
    assert receiver.consume(_Lease()).current_status == 'CURRENT_STAGED'
    assert _input(volume).read('current/latest.json') == newer
    receiver.recover(_Lease())


def test_skips_intermediate_snapshots_and_never_reads_facts(setup_receiver):
    volume, allowed, receiver = setup_receiver
    pin = _pin()
    _head(volume, pin)
    engine = _engine(volume)
    engine.replace('current/latest.json', _current(pin, as_of='2026-09-28T14:05:00Z'))
    latest = _current(pin, as_of='2026-09-28T14:10:00Z')
    engine.replace('current/latest.json', latest)
    engine.replace('facts/facts-' + 'f' * 64 + '.json', {'broken': True})
    engine.replace('state/facts-export-cursor.json', {'broken': True})
    result = receiver.consume(_Lease())
    assert result.current_status == 'CURRENT_STAGED'
    assert _input(volume).read('current/latest.json') == latest
    assert not (receiver.inbox_root / 'facts').exists()
    assert _input(volume).read('state/facts-consumption-cursor.json') is None
    receiver.recover(_Lease())


def test_mismatched_effective_waits_without_receiving_other_configuration(setup_receiver):
    volume, allowed, receiver = setup_receiver
    a, b = _pin('a'), _pin('b')
    allowed[b.result_id] = b
    _head(volume, a)
    engine = _engine(volume)
    previous = _current(a)
    engine.replace('current/latest.json', previous)
    assert receiver.consume(_Lease()).current_status == 'CURRENT_STAGED'
    _head(volume, b)
    lease = _Lease()
    assert receiver.consume(lease).current_status == 'WAITING_CURRENT'
    assert lease.writes == 0
    assert _input(volume).read('current/latest.json') == previous
    latest = _current(b, as_of='2026-09-28T14:10:00Z')
    engine.replace('current/latest.json', latest)
    assert receiver.consume(_Lease()).current_status == 'CURRENT_STAGED'
    assert _input(volume).read('current/latest.json') == latest


def test_missing_ready_blocks_current_without_overwriting_previous(setup_receiver, monkeypatch):
    volume, allowed, receiver = setup_receiver
    pin = _pin()
    _head(volume, pin)
    previous = _current(pin)
    _engine(volume).replace('current/latest.json', previous)
    receiver.consume(_Lease())
    newer = _current(pin, as_of='2026-09-28T14:10:00Z')
    _engine(volume).replace('current/latest.json', newer)

    class _UnavailableReader:
        def __init__(self, *, root):
            pass

        def read_exact_ready(self, **kwargs):
            raise RuntimeError('unavailable')

    monkeypatch.setattr(receiver_module, 'LocalAlarmMaterializationReader', _UnavailableReader)
    with pytest.raises(AlarmDeliveryInputError, match='Exact Delivery configuration'):
        receiver.consume(_Lease())
    assert _input(volume).read('current/latest.json') == previous


def test_checksum_failure_does_not_replace_received_current(setup_receiver):
    volume, allowed, receiver = setup_receiver
    pin = _pin()
    _head(volume, pin)
    previous = _current(pin)
    _engine(volume).replace('current/latest.json', previous)
    receiver.consume(_Lease())
    corrupt = deepcopy(previous)
    corrupt['state']['as_of'] = '2026-09-28T14:10:00Z'
    _engine(volume).replace('current/latest.json', corrupt)
    with pytest.raises(AlarmDeliveryInputError, match='checksum'):
        receiver.consume(_Lease())
    assert _input(volume).read('current/latest.json') == previous


def test_conflicting_same_timestamp_and_backward_snapshot_are_rejected(setup_receiver):
    volume, allowed, receiver = setup_receiver
    pin = _pin()
    _head(volume, pin)
    engine = _engine(volume)
    newer = _current(pin, as_of='2026-09-28T14:10:00Z')
    engine.replace('current/latest.json', newer)
    receiver.consume(_Lease())
    engine.replace('current/latest.json', _current(pin))
    assert receiver.consume(_Lease()).current_status == 'STALE_SOURCE'
    conflict = _current(pin, as_of='2026-09-28T14:10:00Z', alarms=[
        _alarm(as_of='2026-09-28T14:10:00Z')
    ])
    engine.replace('current/latest.json', conflict)
    with pytest.raises(AlarmDeliveryInputError, match='share publication time'):
        receiver.consume(_Lease())
    assert _input(volume).read('current/latest.json') == newer


def test_recovery_rejects_corrupted_received_current(setup_receiver):
    volume, allowed, receiver = setup_receiver
    pin = _pin()
    staged = _current(pin)
    staged['sha256'] = '0' * 64
    _input(volume).replace('current/latest.json', staged)
    with pytest.raises(AlarmDeliveryInputError, match='checksum'):
        receiver.recover(_Lease())


def test_interrupted_receipt_replays_latest_without_partial_cursor(setup_receiver, monkeypatch):
    volume, allowed, receiver = setup_receiver
    pin = _pin()
    _head(volume, pin)
    original = _current(pin)
    _engine(volume).replace('current/latest.json', original)
    receiver.consume(_Lease())
    latest = _current(pin, as_of='2026-09-28T14:10:00Z')
    _engine(volume).replace('current/latest.json', latest)
    original_replace = AtomicJsonStore.replace
    failed = False

    def fail_once(store, path, document):
        nonlocal failed
        if not failed and path == 'current/latest.json' and document == latest:
            failed = True
            raise OSError('Simulated interruption')
        return original_replace(store, path, document)

    monkeypatch.setattr(AtomicJsonStore, 'replace', fail_once)
    with pytest.raises(OSError, match='Simulated interruption'):
        receiver.consume(_Lease())
    assert _input(volume).read('current/latest.json') == original
    assert receiver.consume(_Lease()).current_status == 'CURRENT_STAGED'
    assert _input(volume).read('current/latest.json') == latest
    assert _input(volume).read('state/facts-consumption-cursor.json') is None
