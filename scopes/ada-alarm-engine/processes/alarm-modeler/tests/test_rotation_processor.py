from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ada.processes.alarm_modeler import processor
from ada.processes.alarm_modeler.rotation import ToolRotationMemory

from .test_processor import Context, REF, ReadyStore
from .test_processor import pipeline as pipeline
from .test_projection import alarm, model, source


def _at(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


def _view(destination, key: str) -> list:
    return destination.read('current/latest.json')['tools'][key]['operator_view']


def test_tool_rotation_survives_processor_restart(pipeline, monkeypatch) -> None:
    runner, runtime, current, destination = pipeline
    names = tuple(f'a{i}' for i in range(7))
    monkeypatch.setattr(processor, 'modeler_to_document', lambda _: model(*names))
    runner.clock = lambda: _at(0)
    runtime.replace('runtime/state/effective-head.json', {'artifact_ref': REF})
    current.replace('current/latest.json', source([alarm(name) for name in names]))
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    initial = _view(destination, 'tool-a')
    restarted = processor.AlarmModelerProcessor(
        runtime_root=runner.runtime_root, output_root=runner.output_root,
        rotation_seconds=runner.rotation_seconds, max_visible_slots=runner.max_visible_slots,
        clock=lambda: _at(runner.rotation_seconds),
    )
    assert restarted.run_iteration(Context()).status == 'PUBLISHED'
    assert _view(destination, 'tool-a') != initial


def test_independent_tool_deadlines_with_source_changes(pipeline, monkeypatch) -> None:
    runner, runtime, current, destination = pipeline
    a_names = tuple(f'a{i}' for i in range(7))
    b_names = tuple(f'b{i}' for i in range(7))
    config = model(*(a_names + b_names))
    for entry in config['alarms']:
        if entry['identity']['alarm_key'].startswith('b'):
            entry['visual_targets'][0]['tool_key'] = 'tool-b'
    monkeypatch.setattr(processor, 'modeler_to_document', lambda _: config)
    original = ReadyStore.read_ready

    def both(self, **kwargs):
        ready = original(self, **kwargs)
        ready.delivery.publication_tool_keys = ('tool-a', 'tool-b')
        return ready

    monkeypatch.setattr(ReadyStore, 'read_ready', both)
    runtime.replace('runtime/state/effective-head.json', {'artifact_ref': REF})
    at = [_at(0)]
    runner.clock = lambda: at[0]
    current.replace('current/latest.json', source([alarm(name) for name in a_names]))
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    a0 = _view(destination, 'tool-a')
    at[0] = _at(10)
    alarms = [alarm(name) for name in a_names]
    for name in b_names:
        item = alarm(name)
        item['assignments'][0]['tool_key'] = 'tool-b'
        alarms.append(item)
    current.replace('current/latest.json', source(alarms))
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    b10 = _view(destination, 'tool-b')
    at[0] = _at(30)
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    assert _view(destination, 'tool-a') != a0
    assert _view(destination, 'tool-b') == b10
    at[0] = _at(40)
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    assert _view(destination, 'tool-b') != b10


def test_crash_after_latest_before_memory_confirmation_recovers(pipeline, monkeypatch) -> None:
    runner, runtime, current, destination = pipeline
    names = tuple(f'a{i}' for i in range(7))
    monkeypatch.setattr(processor, 'modeler_to_document', lambda _: model(*names))
    runtime.replace('runtime/state/effective-head.json', {'artifact_ref': REF})
    current.replace('current/latest.json', source([alarm(name) for name in names]))
    runner.clock = lambda: _at(0)
    original = ToolRotationMemory.confirm
    invoked = [False]

    def interrupted(self, **kwargs):
        if not invoked[0]:
            invoked[0] = True
            raise RuntimeError('simulated interruption')
        return original(self, **kwargs)

    monkeypatch.setattr(ToolRotationMemory, 'confirm', interrupted)
    with pytest.raises(RuntimeError, match='simulated interruption'):
        runner.run_iteration(Context())
    published = _view(destination, 'tool-a')
    recovered = processor.AlarmModelerProcessor(
        runtime_root=runner.runtime_root, output_root=runner.output_root,
        rotation_seconds=30, max_visible_slots=runner.max_visible_slots,
        clock=lambda: _at(1),
    )
    assert recovered.run_iteration(Context()).status == 'SKIPPED'
    assert _view(destination, 'tool-a') == published
    assert recovered.run_iteration(Context()).status == 'SKIPPED'
