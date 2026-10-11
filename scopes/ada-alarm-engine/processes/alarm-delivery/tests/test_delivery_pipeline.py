from __future__ import annotations

from copy import deepcopy
from threading import Lock

import pytest

from ada.processes.alarm_delivery.checkpoint import (
    AlarmDeliveryCheckpointError,
    AlarmDeliveryCheckpointStore,
)
from ada.processes.alarm_delivery.contract import plan_tool_deliveries
from ada.processes.alarm_delivery.job import AlarmDeliveryJob, AlarmDeliveryPublicationError
from ada.processes.alarm_delivery.reader import ModelerCurrentReader
from ada.processes.alarm_delivery.transport import (
    LIVE_CONTAINER,
    ParallelCosmosPublisher,
    destination_identity,
    live_document,
)
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.state import AtomicJsonStore

from .test_contract import _seal, _source, _tool


class Context:
    def __init__(self):
        self.memory = {}
        self.facts = {}
        self.work = 0
        self.active = True

    def assert_lease_current(self):
        if not self.active:
            raise RuntimeError('Lease lost')

    def set_memory(self, key, value):
        self.memory[key] = value

    def get_memory(self, key):
        return self.memory.get(key)

    def set_iteration_fact(self, key, value):
        self.facts[key] = value

    def mark_iteration_work(self):
        self.work += 1


class Writer:
    def __init__(self, settings, writes, failures, lock):
        self.settings = settings
        self.writes = writes
        self.failures = failures
        self.lock = lock

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def upsert_item(self, *, container_name, item):
        with self.lock:
            if self.settings.database_name in self.failures:
                raise RuntimeError('Cosmos unavailable')
            self.writes.append((self.settings.database_name, container_name, deepcopy(item)))
        return item


def _connections():
    return {
        key: CosmosSettings(
            endpoint=f'https://{key}.documents.azure.com:443/',
            database_name=key,
            key='testing-key',
        )
        for key in ('tool_a', 'tool_b')
    }


def _pipeline(tmp_path):
    reader = ModelerCurrentReader(root=tmp_path / 'modeler-output')
    checkpoint = AlarmDeliveryCheckpointStore(
        root=tmp_path / 'delivery-state', modeler_application='alarm-modeler'
    )
    writes = []
    failures = set()
    lock = Lock()
    connections = _connections()
    publisher = ParallelCosmosPublisher(
        connections=connections,
        max_workers=2,
        client_factory=lambda settings: Writer(settings, writes, failures, lock),
    )
    job = AlarmDeliveryJob(
        reader=reader, checkpoint=checkpoint, publisher=publisher, connections=connections
    )
    output = AtomicJsonStore(root_path=tmp_path / 'modeler-output')
    return job, output, writes, failures


def test_no_source_waits_and_recovery_precedes_iteration(tmp_path):
    job, _output, writes, _failures = _pipeline(tmp_path)
    context = Context()
    try:
        with pytest.raises(RuntimeError, match='recovery must precede'):
            job.run_iteration(context)
        job.recover(context)
        assert job.run_iteration(context).status == 'WAITING_MODELER'
        assert writes == []
    finally:
        job.publisher.close()


def test_multi_tool_publish_once_and_survive_restart(tmp_path):
    job, output, writes, _failures = _pipeline(tmp_path)
    context = Context()
    try:
        output.replace('current/latest.json', _source())
        job.recover(context)
        result = job.run_iteration(context)
        assert result.status == 'PUBLISHED'
        assert result.published_tools == ('tool_a', 'tool_b')
        assert len(writes) == 2
        assert {item[0] for item in writes} == {'tool_a', 'tool_b'}
        assert {item[1] for item in writes} == {LIVE_CONTAINER}
        assert {item[2]['id'] for item in writes} == {'alarm-live:tool_a', 'alarm-live:tool_b'}
        assert job.run_iteration(context).status == 'UNCHANGED'
        assert len(writes) == 2
    finally:
        job.publisher.close()
    restarted, _output, restarted_writes, _failures = _pipeline(tmp_path)
    next_context = Context()
    try:
        restarted.recover(next_context)
        assert restarted.run_iteration(next_context).status == 'UNCHANGED'
        assert restarted_writes == []
    finally:
        restarted.publisher.close()


def test_partial_failure_confirmed_tool_is_not_republished(tmp_path):
    job, output, writes, failures = _pipeline(tmp_path)
    context = Context()
    try:
        output.replace('current/latest.json', _source())
        job.recover(context)
        failures.add('tool_b')
        with pytest.raises(AlarmDeliveryPublicationError, match='destinations failed'):
            job.run_iteration(context)
        assert [item[0] for item in writes] == ['tool_a']
        assert set(job.checkpoint.read()) == {'tool_a'}
        failures.clear()
        result = job.run_iteration(context)
        assert result.published_tools == ('tool_b',)
        assert result.unchanged_tools == ('tool_a',)
        assert [item[0] for item in writes].count('tool_a') == 1
        assert [item[0] for item in writes].count('tool_b') == 1
    finally:
        job.publisher.close()


def test_only_changed_tool_and_retirement_are_published(tmp_path):
    job, output, writes, _failures = _pipeline(tmp_path)
    context = Context()
    try:
        output.replace('current/latest.json', _source())
        job.recover(context)
        job.run_iteration(context)
        changed = _source(position=2)
        changed['tools']['tool_b']['alarms']['incident'] = {'status': 'ACTIVE'}
        changed['tools']['tool_b']['meta']['live_count'] = 1
        output.replace('current/latest.json', _seal(changed))
        assert job.run_iteration(context).published_tools == ('tool_b',)
        retired = _source(position=3)
        retired['tools']['tool_a'] = _tool('tool_a', retired=True)
        retired['tools']['tool_b'] = deepcopy(changed['tools']['tool_b'])
        output.replace('current/latest.json', _seal(retired))
        assert job.run_iteration(context).published_tools == ('tool_a',)
        assert writes[-1][2]['retired'] is True
        assert writes[-1][2]['alarms'] == {}
    finally:
        job.publisher.close()


def test_source_changed_during_preflight_does_not_publish(tmp_path):
    job, output, writes, _failures = _pipeline(tmp_path)
    context = Context()
    try:
        original_read = job.reader.read
        reads = [0]

        def changing_read():
            reads[0] += 1
            if reads[0] == 2:
                return _source(position=2)
            return _source()

        job.reader.read = changing_read
        job.recover(context)
        assert job.run_iteration(context).status == 'SOURCE_CHANGED'
        assert writes == []
        job.reader.read = original_read
    finally:
        job.publisher.close()


def test_checkpoint_rejects_corruption_and_cannot_regress(tmp_path):
    job, output, writes, _failures = _pipeline(tmp_path)
    context = Context()
    try:
        output.replace('current/latest.json', _source(position=2))
        job.recover(context)
        job.run_iteration(context)
        output.replace('current/latest.json', _source(position=1))
        with pytest.raises(ValueError, match='precedes'):
            job.run_iteration(context)
        store = AtomicJsonStore(root_path=tmp_path / 'delivery-state')
        value = store.read('state/confirmations.json')
        value['confirmations']['tool_a']['semantic_sha256'] = 'a' * 64
        store.replace('state/confirmations.json', value)
        with pytest.raises(AlarmDeliveryCheckpointError, match='integrity'):
            job.checkpoint.read()
    finally:
        job.publisher.close()


def test_destination_change_reissues_without_semantic_change(tmp_path):
    job, output, writes, _failures = _pipeline(tmp_path)
    context = Context()
    try:
        output.replace('current/latest.json', _source())
        job.recover(context)
        job.run_iteration(context)
        changed = CosmosSettings(
            endpoint='https://tool-b-new.documents.azure.com:443/',
            database_name='tool_b_new',
            key='different-key',
        )
        job.connections = {**job.connections, 'tool_b': changed}
        job.publisher._connections['tool_b'] = changed
        assert job.run_iteration(context).published_tools == ('tool_b',)
        assert writes[-1][0] == 'tool_b_new'
    finally:
        job.publisher.close()


def test_live_document_is_stable_and_contains_tool_only():
    source = _source()
    source['tools']['tool_a']['alarms'] = {'occ-a': {'status': 'ACTIVE'}}
    source['tools']['tool_a']['meta']['live_count'] = 1
    plan = plan_tool_deliveries(
        modeler_document=_seal(source),
        destination_identities={
            key: destination_identity(value) for key, value in _connections().items()
        },
        confirmations={},
    )
    doc = live_document(plan.pending[0])
    assert doc['id'] == 'alarm-live:tool_a'
    assert doc['alarms'] == {'occ-a': {'status': 'ACTIVE'}}
    assert doc['tool_key'] == 'tool_a'
    assert doc['artifact_ref']['resolution_key'] == source['artifact_ref']['resolution_key']
    assert 'tool_b' not in str(doc)


def test_corrupted_modeler_source_prevents_all_cosmos_writes(tmp_path):
    job, output, writes, _failures = _pipeline(tmp_path)
    context = Context()
    try:
        source = _source()
        source['sha256'] = '0' * 64
        output.replace('current/latest.json', source)
        job.recover(context)
        with pytest.raises(ValueError, match='checksum'):
            job.run_iteration(context)
        assert writes == []
        assert job.checkpoint.read() == {}
    finally:
        job.publisher.close()


def test_parallel_dispatch_has_overlapping_tool_writes():
    from threading import Barrier

    barrier = Barrier(2)
    writes = []
    lock = Lock()

    class ConcurrentWriter(Writer):
        def upsert_item(self, *, container_name, item):
            barrier.wait(timeout=5)
            return super().upsert_item(container_name=container_name, item=item)

    connections = _connections()
    publisher = ParallelCosmosPublisher(
        connections=connections,
        max_workers=2,
        client_factory=lambda settings: ConcurrentWriter(settings, writes, set(), lock),
    )
    plan = plan_tool_deliveries(
        modeler_document=_source(),
        destination_identities={
            key: destination_identity(value) for key, value in connections.items()
        },
        confirmations={},
    )
    try:
        results = publisher.publish(plan.pending, assert_authority=lambda: None)
        assert len(results) == 2
        assert all(result.successful for result in results)
        assert len(writes) == 2
    finally:
        publisher.close()


def test_lost_lease_after_write_does_not_confirm(tmp_path):
    job, output, writes, _failures = _pipeline(tmp_path)
    context = Context()
    original_factory = job.publisher._factory

    class LoseLeaseWriter(Writer):
        def upsert_item(self, *, container_name, item):
            result = super().upsert_item(container_name=container_name, item=item)
            context.active = False
            return result

    job.publisher._factory = lambda settings: LoseLeaseWriter(settings, writes, set(), Lock())
    try:
        output.replace('current/latest.json', _source())
        job.recover(context)
        with pytest.raises(RuntimeError, match='Lease lost'):
            job.run_iteration(context)
        assert job.checkpoint.read() == {}
        context.active = True
        job.publisher._factory = original_factory
        assert job.run_iteration(context).published_tools == ('tool_a', 'tool_b')
    finally:
        job.publisher.close()
