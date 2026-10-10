from __future__ import annotations

from types import SimpleNamespace

from ada.processes.alarm_runtime.composition import AlarmRuntimeComposition


def test_checkpoint_runs_periodically_and_on_rotation(monkeypatch) -> None:
    now = [100.0]
    monkeypatch.setattr('ada.processes.alarm_runtime.composition.monotonic', lambda: now[0])
    position = SimpleNamespace(segment_id='2026-08-23T20Z#0000')
    head = SimpleNamespace(aligned=True, durable=position)
    calls = []

    class Persistence:
        def read_head(self):
            return head

        def publish_recovery_checkpoint(self, **kwargs):
            calls.append('checkpoint')
            return True

        def compact_recovered_wal(self, **kwargs):
            calls.append('compact')
            return 0

    class Publications:
        persistence = Persistence()
        facts = SimpleNamespace(exported_position=lambda: position)

        def reconcile(self, context, *, force=False):
            calls.append('reconcile')
            return False

    class Job:
        def run_iteration(self, context):
            calls.append('iteration')
            return object()

    composition = AlarmRuntimeComposition(
        configuration=None,
        runtime_configuration=None,
        settings=SimpleNamespace(checkpoint_interval_seconds=60),
        job=Job(),
        publications=Publications(),
        definition=None,
    )
    context = SimpleNamespace(
        assert_lease_current=lambda: None,
        fenced_mutation=lambda: None,
    )
    composition.run_iteration(context)
    assert calls.count('checkpoint') == 1
    now[0] = 130.0
    composition.run_iteration(context)
    assert calls.count('checkpoint') == 1
    position.segment_id = '2026-08-23T20Z#0001'
    composition.run_iteration(context)
    assert calls.count('checkpoint') == 2
    now[0] = 195.0
    composition.run_iteration(context)
    assert calls.count('checkpoint') == 3
    assert calls.count('compact') == 3
