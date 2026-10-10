from __future__ import annotations

from types import SimpleNamespace

from ada.processes.alarm_runtime import composition as runtime


class _Persistence:
    def __init__(self):
        self.head = SimpleNamespace(durable=SimpleNamespace(segment_id='segment'), aligned=True)
        self.recovery_checkpoints = 0
        self.compaction_positions = []

    def read_head(self):
        return self.head

    def publish_recovery_checkpoint(self, **kwargs):
        self.recovery_checkpoints += 1

    def compact_recovered_wal(self, *, exported_through, **kwargs):
        self.compaction_positions.append(exported_through)


class _Facts:
    def __init__(self, owner):
        self.owner = owner

    def exported_position(self):
        assert self.owner.calls[-1][1]
        return 'confirmed-exported-position'


class _Publications:
    def __init__(self):
        self.persistence = _Persistence()
        self.calls = []
        self.facts = _Facts(self)

    def reconcile(self, context, *, force=False, publish_facts=True):
        self.calls.append((force, publish_facts))
        return True


class _Job:
    def __init__(self):
        self.iterations = 0

    def recover(self, context):
        return 'recovered'

    def run_iteration(self, context):
        self.iterations += 1
        return SimpleNamespace(outcome='UNCHANGED')


def _composition():
    return runtime.AlarmRuntimeComposition(
        configuration=object(),
        runtime_configuration=object(),
        settings=SimpleNamespace(
            facts_publish_interval_seconds=10.0,
            checkpoint_interval_seconds=60.0,
        ),
        job=_Job(),
        publications=_Publications(),
        definition=object(),
    )


def test_facts_publication_interval_does_not_change_evaluation_cadence(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(runtime, 'monotonic', lambda: clock[0])
    composition = _composition()
    composition._last_maintenance_at = 100.0
    composition._last_maintenance_segment = 'segment'
    assert composition.recover(object()) == 'recovered'
    assert composition.publications.calls == [(True, True)]
    clock[0] = 101.0
    composition.run_iteration(object())
    assert composition.publications.calls[-2:] == [(False, False), (False, False)]
    clock[0] = 109.0
    composition.run_iteration(object())
    assert composition.publications.calls[-2:] == [(False, False), (False, False)]
    clock[0] = 110.0
    composition.run_iteration(object())
    assert composition.publications.calls[-2:] == [(False, False), (False, True)]
    assert composition.job.iterations == 3


def test_checkpoint_forces_export_before_wal_compaction(monkeypatch):
    monkeypatch.setattr(runtime, 'monotonic', lambda: 42.0)
    composition = _composition()
    context = SimpleNamespace(assert_lease_current=lambda: None, fenced_mutation=lambda: None)
    composition.checkpoint(context)
    assert composition.publications.calls == [(False, True)]
    assert composition.publications.persistence.recovery_checkpoints == 1
    assert composition.publications.persistence.compaction_positions == [
        'confirmed-exported-position'
    ]
    assert composition._last_facts_publication_at == 42.0


def test_failed_export_prevents_wal_compaction(monkeypatch):
    composition = _composition()

    def fail_export(context, *, force=False, publish_facts=True):
        raise OSError('export failed')

    monkeypatch.setattr(composition.publications, 'reconcile', fail_export)
    context = SimpleNamespace(assert_lease_current=lambda: None, fenced_mutation=lambda: None)
    try:
        composition.checkpoint(context)
    except OSError as error:
        assert str(error) == 'export failed'
    else:
        raise AssertionError('checkpoint must propagate export failure')
    assert composition.publications.persistence.recovery_checkpoints == 0
    assert composition.publications.persistence.compaction_positions == []
