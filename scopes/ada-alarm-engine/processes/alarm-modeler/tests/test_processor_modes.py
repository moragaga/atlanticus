from __future__ import annotations

from datetime import UTC, datetime

from ada.processes.alarm_modeler import processor

from .test_processor import Context, REF, ReadyStore
from .test_processor import pipeline as pipeline
from .test_projection import alarm, model, source


def test_grouped_process_does_not_republish_without_normal_rotation(pipeline, monkeypatch):
    runner, runtime, current, destination = pipeline
    names = ('d1', 'd2', 'n1', 'n2', 'n3', 'n4', 'n5')
    configuration = model(*names)
    for entry in configuration['alarms']:
        entry['visual_targets'][0]['process_projection_mode'] = (
            'DISTRIBUTED' if entry['identity']['alarm_key'].startswith('d') else 'GENERIC'
        )
    monkeypatch.setattr(processor, 'modeler_to_document', lambda value: configuration)
    clock = [datetime.fromtimestamp(0, tz=UTC)]
    runner.clock = lambda: clock[0]
    runtime.replace('runtime/state/effective-head.json', {'artifact_ref': REF})
    current.replace('current/latest.json', source([alarm(name) for name in names]))
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    original = destination.read('current/latest.json')
    assert len(original['tools']['tool-a']['operator_pool']) == 7
    assert original['tools']['tool-a']['meta']['rotation_pending'] is False
    clock[0] = datetime.fromtimestamp(30, tz=UTC)
    assert runner.run_iteration(Context()).status == 'SKIPPED'
    assert ReadyStore.reads == 1
    assert destination.read('current/latest.json') == original


def test_grouped_process_republishes_on_normal_rotation(pipeline, monkeypatch):
    runner, runtime, current, destination = pipeline
    names = ('d1', 'd2', 'n1', 'n2', 'n3', 'n4', 'n5', 'n6')
    configuration = model(*names)
    for entry in configuration['alarms']:
        entry['visual_targets'][0]['process_projection_mode'] = (
            'DISTRIBUTED' if entry['identity']['alarm_key'].startswith('d') else 'GENERIC'
        )
    monkeypatch.setattr(processor, 'modeler_to_document', lambda value: configuration)
    clock = [datetime.fromtimestamp(0, tz=UTC)]
    runner.clock = lambda: clock[0]
    runtime.replace('runtime/state/effective-head.json', {'artifact_ref': REF})
    current.replace('current/latest.json', source([alarm(name) for name in names]))
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    initial_view = destination.read('current/latest.json')['tools']['tool-a']['operator_view']
    clock[0] = datetime.fromtimestamp(30, tz=UTC)
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    next_view = destination.read('current/latest.json')['tools']['tool-a']['operator_view']
    assert initial_view[:5] != next_view[:5]
    assert initial_view[-1] == next_view[-1]
    assert ReadyStore.reads == 2
