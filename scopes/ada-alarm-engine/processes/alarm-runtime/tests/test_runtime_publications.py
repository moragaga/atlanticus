from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from ada.alarms.persistence.operational import (
    AlarmPersistence,
    AlarmRecoveryRequiredError,
    JournalHead,
)
from ada.processes.alarm_runtime.composition import AlarmRuntimeComposition
from ada.processes.alarm_runtime.publication import (
    AlarmCommittedFactsExporter,
    AlarmDurableCurrentPublisher,
)
from ada.processes.alarm_runtime.publication.operational import AlarmDurablePublications
from atlanticus.state import AtomicJsonStore

from .test_output_current import _commit, _init


class _Context:
    def assert_lease_current(self):
        return None

    def fenced_mutation(self):
        return nullcontext()


def _service(tmp_path, persistence):
    root = tmp_path / 'runtime' / 'alarms' / 'output'
    return AlarmDurablePublications(
        persistence=persistence,
        facts=AlarmCommittedFactsExporter(root=root, source_key='alarm-configuration'),
        current=AlarmDurableCurrentPublisher(root=root, source_key='alarm-configuration'),
    )


def _output(tmp_path):
    return AtomicJsonStore(root_path=tmp_path / 'runtime' / 'alarms' / 'output')


def test_genesis_does_not_fabricate_current_without_effective(tmp_path):
    persistence = AlarmPersistence(application_root=tmp_path / 'runtime')
    persistence.recover(assert_authority=lambda: None, fenced_mutation=nullcontext)
    service = _service(tmp_path, persistence)
    assert not service.reconcile(_Context())
    assert _output(tmp_path).read('current/durable-latest.json') is None
    cursor = _output(tmp_path).read('state/facts-export-cursor.json')
    assert cursor['schema_version'] == 3
    assert cursor['journal_position'] is None
    assert not service.reconcile(_Context())


def test_first_effective_without_groups_publishes_valid_empty_current(tmp_path):
    persistence = _init(tmp_path)
    service = _service(tmp_path, persistence)
    assert service.reconcile(_Context())
    document = _output(tmp_path).read('current/durable-latest.json')
    assert document['state']['groups'] == []
    assert document['journal_position'] == persistence.read_head().durable.as_document()
    assert not service.reconcile(_Context())


def test_mp10_open_close_restarts_idempotently_with_two_facts_batches(tmp_path):
    persistence = _init(tmp_path)
    service = _service(tmp_path, persistence)
    assert service.reconcile(_Context())
    start = _commit(persistence, offset=1, opened=True)
    assert service.reconcile(_Context())
    opened = _output(tmp_path).read('current/durable-latest.json')
    alarm = opened['state']['groups'][0]['alarms']['mp10/high_temperature']
    assert alarm['occurrence']['occurrence_id'] == 'occ-mp10-1'
    assert opened['journal_position']['commit_id'] == start.commit.commit_id
    assert not service.reconcile(_Context())

    end = _commit(persistence, offset=3, opened=False)
    assert service.reconcile(_Context())
    closed = _output(tmp_path).read('current/durable-latest.json')
    assert closed['journal_position']['commit_id'] == end.commit.commit_id
    assert closed['state']['groups'][0]['alarms'] == {}
    facts_root = tmp_path / 'runtime' / 'alarms' / 'output' / 'facts'
    facts_files = sorted(facts_root.glob('facts-*.json'))
    assert len(facts_files) == 2
    cursor = _output(tmp_path).read('state/facts-export-cursor.json')
    assert cursor['journal_position'] == persistence.read_head().durable.as_document()

    restarted = AlarmPersistence(application_root=tmp_path / 'runtime')
    restarted.recover(assert_authority=lambda: None, fenced_mutation=nullcontext)
    assert not _service(tmp_path, restarted).reconcile(_Context(), force=True)
    assert _output(tmp_path).read('current/durable-latest.json') == closed
    assert len(list(facts_root.glob('facts-*.json'))) == 2


def test_facts_checkpoint_write_failure_retries_without_repeating_commit(tmp_path, monkeypatch):
    persistence = _init(tmp_path)
    service = _service(tmp_path, persistence)
    service.reconcile(_Context())
    baseline = _output(tmp_path).read('current/durable-latest.json')
    _commit(persistence, offset=1, opened=True)
    original = AtomicJsonStore.replace
    failed = False

    def fail_once(self, name, document):
        nonlocal failed
        if name == 'state/facts-export-cursor.json' and not failed:
            failed = True
            raise OSError('forced facts publication error')
        return original(self, name, document)

    monkeypatch.setattr(AtomicJsonStore, 'replace', fail_once)
    with pytest.raises(OSError, match='forced facts'):
        service.reconcile(_Context())
    assert _output(tmp_path).read('current/durable-latest.json') == baseline
    assert len(persistence.read_durable_records()) == 1
    assert service.reconcile(_Context())
    assert not service.reconcile(_Context())
    assert len(persistence.read_durable_records()) == 1
    facts_root = tmp_path / 'runtime' / 'alarms' / 'output' / 'facts'
    assert len(list(facts_root.glob('facts-*.json'))) == 1


def test_current_failure_after_facts_reconciles_on_retry(tmp_path, monkeypatch):
    persistence = _init(tmp_path)
    service = _service(tmp_path, persistence)
    service.reconcile(_Context())
    baseline = _output(tmp_path).read('current/durable-latest.json')
    _commit(persistence, offset=1, opened=True)
    original = AlarmDurableCurrentPublisher.publish
    failed = False

    def fail_once(self, *, context, persistence):
        nonlocal failed
        if not failed:
            failed = True
            raise OSError('forced current publication error')
        return original(self, context=context, persistence=persistence)

    monkeypatch.setattr(AlarmDurableCurrentPublisher, 'publish', fail_once)
    with pytest.raises(OSError, match='forced current'):
        service.reconcile(_Context())
    cursor = _output(tmp_path).read('state/facts-export-cursor.json')
    assert cursor['journal_position'] == persistence.read_head().durable.as_document()
    assert _output(tmp_path).read('current/durable-latest.json') == baseline
    assert service.reconcile(_Context())
    assert not service.reconcile(_Context(), force=True)
    facts_root = tmp_path / 'runtime' / 'alarms' / 'output' / 'facts'
    assert len(list(facts_root.glob('facts-*.json'))) == 1


def test_unaligned_wal_blocks_publication(tmp_path, monkeypatch):
    persistence = _init(tmp_path)
    service = _service(tmp_path, persistence)
    valid = persistence.read_head()
    monkeypatch.setattr(
        persistence, 'read_head',
        lambda: JournalHead(durable=valid.durable, materialized=None),
    )
    with pytest.raises(AlarmRecoveryRequiredError, match='aligned'):
        service.reconcile(_Context())
    assert _output(tmp_path).read('current/durable-latest.json') is None


def test_no_wal_change_skips_expensive_provenance_replay(tmp_path, monkeypatch):
    persistence = _init(tmp_path)
    service = _service(tmp_path, persistence)
    service.reconcile(_Context())

    def unexpected(*args, **kwargs):
        raise AssertionError('unexpected full provenance read')

    monkeypatch.setattr(persistence, 'read_durable_provenance', unexpected)
    assert not service.reconcile(_Context())
    with pytest.raises(AssertionError, match='provenance'):
        service.reconcile(_Context(), force=True)


def test_rejects_publishers_with_different_output_roots(tmp_path):
    persistence = _init(tmp_path)
    with pytest.raises(ValueError, match='share output root'):
        AlarmDurablePublications(
            persistence=persistence,
            facts=AlarmCommittedFactsExporter(
                root=tmp_path / 'a', source_key='alarm-configuration'
            ),
            current=AlarmDurableCurrentPublisher(
                root=tmp_path / 'b', source_key='alarm-configuration'
            ),
        )


class _Job:
    def __init__(self, events):
        self.events = events

    def recover(self, context):
        self.events.append('recover')
        return 'authority'

    def run_iteration(self, context):
        self.events.append('commit')
        return 'result'


class _Publications:
    def __init__(self, events):
        self.events = events
        self.fail_after_commit = False

    def reconcile(self, context, *, force=False):
        self.events.append('force' if force else 'publish')
        if self.fail_after_commit and self.events[-2:] == ['commit', 'publish']:
            self.fail_after_commit = False
            raise OSError('publication interrupted')
        return False


def _composition(events):
    return AlarmRuntimeComposition(
        configuration=SimpleNamespace(values={}),
        runtime_configuration=None,
        settings=None,
        job=_Job(events),
        publications=_Publications(events),
        definition=None,
    )


def test_composition_recovers_before_publication_and_commits_before_outputs():
    events = []
    composition = _composition(events)
    assert composition.recover(_Context()) == 'authority'
    assert composition.run_iteration(_Context()) == 'result'
    assert events == ['recover', 'force', 'publish', 'commit', 'publish']


def test_composition_retries_publication_before_next_cycle_after_failure():
    events = []
    composition = _composition(events)
    composition.publications.fail_after_commit = True
    with pytest.raises(OSError, match='publication interrupted'):
        composition.run_iteration(_Context())
    assert events == ['publish', 'commit', 'publish']
    assert composition.run_iteration(_Context()) == 'result'
    assert events == ['publish', 'commit', 'publish', 'publish', 'commit', 'publish']


def test_restart_repairs_missing_current_from_durable_wal(tmp_path):
    persistence = _init(tmp_path)
    service = _service(tmp_path, persistence)
    assert service.reconcile(_Context())
    _commit(persistence, offset=1, opened=True)
    assert service.reconcile(_Context())
    good = _output(tmp_path).read('current/durable-latest.json')
    latest = tmp_path / 'runtime' / 'alarms' / 'output' / 'current' / 'durable-latest.json'
    latest.unlink()

    restarted = AlarmPersistence(application_root=tmp_path / 'runtime')
    restarted.recover(assert_authority=lambda: None, fenced_mutation=nullcontext)
    assert _service(tmp_path, restarted).reconcile(_Context(), force=True)
    assert _output(tmp_path).read('current/durable-latest.json') == good
    assert len(restarted.read_durable_records()) == 1


def test_composition_preflight_failure_prevents_new_commit():
    events = []
    composition = _composition(events)

    def fail_before_cycle(context, *, force=False):
        events.append('publish')
        raise OSError('backlog publication failed')

    composition.publications.reconcile = fail_before_cycle
    with pytest.raises(OSError, match='backlog publication'):
        composition.run_iteration(_Context())
    assert events == ['publish']


def test_execute_wires_recovery_and_iteration_wrappers(monkeypatch):
    from ada.processes.alarm_runtime import composition as module

    events = []
    composition = _composition(events)
    captured = {}

    def execute_job(**kwargs):
        captured.update(kwargs)
        return 'executed'

    monkeypatch.setattr(module, 'execute_job', execute_job)
    assert composition.execute(argv=('dry-run',)) == 'executed'
    assert captured['argv'] == ('dry-run',)
    assert captured['iteration'].__self__ is composition
    assert captured['iteration'].__func__ is AlarmRuntimeComposition.run_iteration
    assert captured['recovery'].__self__ is composition
    assert captured['recovery'].__func__ is AlarmRuntimeComposition.recover
