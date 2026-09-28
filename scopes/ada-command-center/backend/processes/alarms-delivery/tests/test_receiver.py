from __future__ import annotations

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from ada_command_center.alarms.persistence import (
    AlarmArtifactRefSnapshot,
    AlarmEffectiveConfigurationHead,
    EngineCommitMetadata,
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


def _current(pin, *, as_of=_AT, alarms=None):
    content = {
        'document_type': 'ada_command_center_engine_resolved_current_state',
        'schema_version': 1,
        'artifact_ref': pin.as_document(),
        'state': {
            'resolution_key': pin.as_document()['resolution_key'],
            'as_of': as_of,
            'alarms': [] if alarms is None else alarms,
        },
    }
    content['sha256'] = receiver_module._hash(content)
    return content


def _fact(pin, *, offset, code):
    commit = EngineCommitMetadata(
        commit_id=f'commit-{offset}',
        cycle_id=f'cycle-{offset}',
        priority_group='mine',
        previous_commit_id=None if offset == 2 else f'commit-{offset - 1}',
        evaluated_at=_AT,
        committed_at=_AT,
        alarm_configuration_revision='R10',
        tool_registry_revision='C5',
        runtime_artifact_version='1.0.0',
        affected_alarms=('mine/temperature',),
    )
    position = JournalPosition(segment_id=_SEGMENT, byte_offset=offset, commit_id=commit.commit_id)
    batch = {
        'document_type': 'ada_command_center_engine_committed_facts_batch',
        'schema_version': 2,
        'batch_id': f'facts-{code * 64}',
        'artifact_ref': pin.as_document(),
        'journal_position': position.as_document(),
        'commit': commit.as_document(),
        'commit_record_hash': 'sha256:' + code * 64,
        'previous_batch': None,
        'records': {'journey_events': [{'event_id': f'event-{offset}'}]},
    }
    batch['sha256'] = receiver_module._hash(batch)
    return batch


def _publish_facts(volume, batches):
    store = _engine(volume)
    previous = None
    for batch in batches:
        batch['previous_batch'] = previous
        batch['sha256'] = receiver_module._hash(
            {key: value for key, value in batch.items() if key != 'sha256'}
        )
        store.replace(f'facts/{batch["batch_id"]}.json', batch)
        previous = {'batch_id': batch['batch_id'], 'sha256': batch['sha256']}
    last = batches[-1]
    store.replace(
        'state/facts-export-cursor.json',
        {
            'document_type': 'ada_command_center_engine_facts_export_cursor',
            'schema_version': 2,
            'artifact_ref': last['artifact_ref'],
            'batch_id': last['batch_id'],
            'batch_sha256': last['sha256'],
            'journal_position': last['journal_position'],
        },
    )


@pytest.fixture
def setup_receiver(monkeypatch, tmp_path):
    pin = _pin()

    class _Reader:
        def __init__(self, *, root):
            assert root == tmp_path / 'ada-command-center' / 'alarms' / 'materialization'

        def read_exact_ready(self, *, source_key, result_id, manifest_sha256):
            assert source_key == pin.source_key
            assert result_id == pin.result_id
            assert manifest_sha256 == pin.manifest_sha256
            resolution = SimpleNamespace(
                alarm_configuration_revision=pin.alarm_configuration_revision,
                confirmed_tool_catalog_revision=pin.confirmed_tool_catalog_revision,
            )
            return SimpleNamespace(
                result_id=pin.result_id,
                manifest_sha256=pin.manifest_sha256,
                runtime=SimpleNamespace(resolution_key=resolution),
                delivery=SimpleNamespace(resolution_key=resolution),
            )

    monkeypatch.setattr(receiver_module, 'LocalAlarmMaterializationReader', _Reader)
    return tmp_path, pin, LocalAlarmDeliveryReceiver(tmp_path, _SOURCE)


def test_initial_engine_export_cursor_waits_without_committed_facts(setup_receiver):
    volume, pin, receiver = setup_receiver
    _engine(volume).replace(
        'state/facts-export-cursor.json',
        {
            'document_type': 'ada_command_center_engine_facts_export_cursor',
            'schema_version': 2,
            'artifact_ref': pin.as_document(),
            'batch_id': None,
            'batch_sha256': None,
            'journal_position': None,
        },
    )
    result = receiver.consume(_Lease())
    assert result.current_status == 'WAITING_EFFECTIVE'
    assert result.staged_facts == 0
    assert _input(volume).read('state/facts-consumption-cursor.json') is None


def test_facts_require_canonical_persistence_record_hash(setup_receiver):
    volume, pin, receiver = setup_receiver
    batch = _fact(pin, offset=2, code='a')
    batch['commit_record_hash'] = 'a' * 64
    batch['sha256'] = receiver_module._hash(
        {key: value for key, value in batch.items() if key != 'sha256'}
    )
    _publish_facts(volume, [batch])
    with pytest.raises(AlarmDeliveryInputError, match='commit record identity'):
        receiver.consume(_Lease())


def test_absent_effective_never_invents_empty_current(setup_receiver):
    volume, pin, receiver = setup_receiver
    _engine(volume).replace('current/latest.json', _current(pin))
    result = receiver.consume(_Lease())
    assert result.current_status == 'WAITING_EFFECTIVE'
    assert _input(volume).read('current/latest.json') is None


def test_current_accepts_exact_pin_empty_then_newer_snapshot(setup_receiver):
    volume, pin, receiver = setup_receiver
    _head(volume, pin)
    store = _engine(volume)
    store.replace('current/latest.json', _current(pin))
    assert receiver.consume(_Lease()).current_status == 'CURRENT_STAGED'
    assert receiver.consume(_Lease()).current_status == 'CURRENT_UNCHANGED'
    newer = _current(pin, as_of='2026-09-28T14:00:01Z')
    store.replace('current/latest.json', newer)
    assert receiver.consume(_Lease()).current_status == 'CURRENT_STAGED'
    assert _input(volume).read('current/latest.json') == newer
    receiver.recover(_Lease())


def test_current_waits_when_published_identity_differs_from_effective(setup_receiver):
    volume, pin, receiver = setup_receiver
    _head(volume, _pin('b'))
    _engine(volume).replace('current/latest.json', _current(pin))
    assert receiver.consume(_Lease()).current_status == 'WAITING_CURRENT'
    assert _input(volume).read('current/latest.json') is None


def test_current_corruption_fails_closed_without_overwriting_stage(setup_receiver):
    volume, pin, receiver = setup_receiver
    _head(volume, pin)
    good = _current(pin)
    _engine(volume).replace('current/latest.json', good)
    receiver.consume(_Lease())
    corrupt = json.loads(json.dumps(good))
    corrupt['state']['as_of'] = '2026-09-28T14:00:01Z'
    _engine(volume).replace('current/latest.json', corrupt)
    with pytest.raises(AlarmDeliveryInputError, match='checksum'):
        receiver.consume(_Lease())
    assert _input(volume).read('current/latest.json') == good


def test_facts_read_in_journal_order_and_ack_only_after_staging(setup_receiver):
    volume, pin, receiver = setup_receiver
    receiver.max_facts_per_iteration = 2
    batches = [
        _fact(pin, offset=offset, code=code) for offset, code in [(2, 'a'), (3, 'b'), (4, 'c')]
    ]
    _publish_facts(volume, batches)
    first = receiver.consume(_Lease())
    assert first.staged_facts == 2
    cursor = _input(volume).read('state/facts-consumption-cursor.json')
    assert cursor['batch_id'] == batches[1]['batch_id']
    assert _input(volume).read(f'facts/{batches[0]["batch_id"]}.json') == batches[0]
    second = receiver.consume(_Lease())
    assert second.staged_facts == 1
    assert receiver.consume(_Lease()).staged_facts == 0
    receiver.recover(_Lease())
    assert (
        _input(volume).read('state/facts-consumption-cursor.json')['batch_id']
        == batches[2]['batch_id']
    )


def test_staging_interruption_replays_exact_batch_without_duplication(setup_receiver, monkeypatch):
    volume, pin, receiver = setup_receiver
    batch = _fact(pin, offset=2, code='d')
    _publish_facts(volume, [batch])
    original = AtomicJsonStore.replace
    hit = False

    def interrupted(self, path, value):
        nonlocal hit
        if path == 'state/facts-consumption-cursor.json' and not hit:
            hit = True
            raise OSError('Simulated interruption after staging')
        return original(self, path, value)

    monkeypatch.setattr(AtomicJsonStore, 'replace', interrupted)
    with pytest.raises(OSError, match='Simulated interruption'):
        receiver.consume(_Lease())
    assert _input(volume).read(f'facts/{batch["batch_id"]}.json') == batch
    assert _input(volume).read('state/facts-consumption-cursor.json') is None
    assert receiver.consume(_Lease()).staged_facts == 1
    assert receiver.consume(_Lease()).staged_facts == 0


def test_tampered_exported_facts_block_receipt_and_cursor(setup_receiver):
    volume, pin, receiver = setup_receiver
    batch = _fact(pin, offset=2, code='e')
    _publish_facts(volume, [batch])
    damaged = json.loads(json.dumps(batch))
    damaged['records']['journey_events'][0]['event_id'] = 'changed'
    _engine(volume).replace(f'facts/{batch["batch_id"]}.json', damaged)
    with pytest.raises(AlarmDeliveryInputError, match='checksum'):
        receiver.consume(_Lease())
    assert _input(volume).read('state/facts-consumption-cursor.json') is None


def test_recover_detects_deleted_last_durable_receipt(setup_receiver):
    volume, pin, receiver = setup_receiver
    batch = _fact(pin, offset=2, code='f')
    _publish_facts(volume, [batch])
    receiver.consume(_Lease())
    (_input(volume).path_for(f'facts/{batch["batch_id"]}.json')).unlink()
    with pytest.raises(AlarmDeliveryInputError, match='missing'):
        receiver.recover(_Lease())


def test_facts_copy_does_not_require_current_to_have_been_published(setup_receiver):
    volume, pin, receiver = setup_receiver
    batch = _fact(pin, offset=2, code='a')
    _publish_facts(volume, [batch])
    result = receiver.consume(_Lease())
    assert result.current_status == 'WAITING_EFFECTIVE'
    assert result.staged_facts == 1


def test_uncommitted_orphan_batch_is_not_accepted(setup_receiver):
    volume, pin, receiver = setup_receiver
    batch = _fact(pin, offset=2, code='a')
    _engine(volume).replace(f'facts/{batch["batch_id"]}.json', batch)
    with pytest.raises(AlarmDeliveryInputError, match='without a committed export cursor'):
        receiver.consume(_Lease())
    assert _input(volume).read(f'facts/{batch["batch_id"]}.json') is None


def test_missing_intermediate_export_batch_rejects_all_receipts(setup_receiver):
    volume, pin, receiver = setup_receiver
    batches = [_fact(pin, offset=i, code=c) for i, c in ((2, 'a'), (3, 'b'), (4, 'c'))]
    _publish_facts(volume, batches)
    _engine(volume).path_for(f'facts/{batches[1]["batch_id"]}.json').unlink()
    with pytest.raises(AlarmDeliveryInputError, match='chain'):
        receiver.consume(_Lease())
    assert _input(volume).read('state/facts-consumption-cursor.json') is None
    assert not list((receiver.inbox_root / 'facts').glob('*.json'))


def test_missing_first_export_batch_fails_closed(setup_receiver):
    volume, pin, receiver = setup_receiver
    batches = [_fact(pin, offset=i, code=c) for i, c in ((2, 'a'), (3, 'b'))]
    _publish_facts(volume, batches)
    _engine(volume).path_for(f'facts/{batches[0]["batch_id"]}.json').unlink()
    with pytest.raises(AlarmDeliveryInputError, match='chain'):
        receiver.consume(_Lease())
    assert _input(volume).read('state/facts-consumption-cursor.json') is None


def test_missing_after_partial_receipt_does_not_advance_cursor(setup_receiver):
    volume, pin, receiver = setup_receiver
    receiver.max_facts_per_iteration = 1
    batches = [_fact(pin, offset=i, code=c) for i, c in ((2, 'a'), (3, 'b'), (4, 'c'))]
    _publish_facts(volume, batches)
    assert receiver.consume(_Lease()).staged_facts == 1
    previous_cursor = _input(volume).read('state/facts-consumption-cursor.json')
    _engine(volume).path_for(f'facts/{batches[1]["batch_id"]}.json').unlink()
    with pytest.raises(AlarmDeliveryInputError, match='chain'):
        receiver.consume(_Lease())
    assert _input(volume).read('state/facts-consumption-cursor.json') == previous_cursor


def test_recomputed_batch_checksum_does_not_hide_wrong_previous_link(setup_receiver):
    volume, pin, receiver = setup_receiver
    batches = [_fact(pin, offset=i, code=c) for i, c in ((2, 'a'), (3, 'b'))]
    _publish_facts(volume, batches)
    forged = json.loads(json.dumps(batches[-1]))
    forged['previous_batch']['sha256'] = '0' * 64
    forged['sha256'] = receiver_module._hash({k: v for k, v in forged.items() if k != 'sha256'})
    _engine(volume).replace(f'facts/{forged["batch_id"]}.json', forged)
    cursor = _engine(volume).read('state/facts-export-cursor.json')
    cursor['batch_sha256'] = forged['sha256']
    _engine(volume).replace('state/facts-export-cursor.json', cursor)
    with pytest.raises(AlarmDeliveryInputError, match='chain'):
        receiver.consume(_Lease())
    assert _input(volume).read('state/facts-consumption-cursor.json') is None


def test_recover_audits_historical_receipt_chain_not_only_tip(setup_receiver):
    volume, pin, receiver = setup_receiver
    batches = [_fact(pin, offset=i, code=c) for i, c in ((2, 'a'), (3, 'b'), (4, 'c'))]
    _publish_facts(volume, batches)
    assert receiver.consume(_Lease()).staged_facts == 3
    _input(volume).path_for(f'facts/{batches[1]["batch_id"]}.json').unlink()
    with pytest.raises(AlarmDeliveryInputError, match='missing a prior batch'):
        receiver.recover(_Lease())


def test_legacy_producer_or_consumer_cursor_is_rejected(setup_receiver):
    volume, pin, receiver = setup_receiver
    first = _fact(pin, offset=2, code='a')
    _publish_facts(volume, [first])
    cursor = _engine(volume).read('state/facts-export-cursor.json')
    cursor['schema_version'] = 1
    _engine(volume).replace('state/facts-export-cursor.json', cursor)
    with pytest.raises(AlarmDeliveryInputError, match='export cursor is invalid'):
        receiver.consume(_Lease())
    cursor['schema_version'] = 2
    _engine(volume).replace('state/facts-export-cursor.json', cursor)
    assert receiver.consume(_Lease()).staged_facts == 1
    received = _input(volume).read('state/facts-consumption-cursor.json')
    received['schema_version'] = 1
    _input(volume).replace('state/facts-consumption-cursor.json', received)
    with pytest.raises(AlarmDeliveryInputError, match='receipt cursor is invalid'):
        receiver.recover(_Lease())
