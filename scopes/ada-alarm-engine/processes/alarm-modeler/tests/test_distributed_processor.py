from __future__ import annotations

from datetime import UTC, datetime

from ada.processes.alarm_modeler import processor
from ada.processes.alarm_modeler.presentation_policy import CAROUSEL_ROTATION_SECONDS
from ada.processes.alarm_modeler.rotation import ToolRotationMemory

from .test_processor import Context, REF
from .test_processor import pipeline as pipeline
from .test_projection import alarm, model, source


def _at(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


def _configuration(names: tuple[str, ...]) -> dict:
    configuration = model(*names)
    for entry in configuration['alarms']:
        name = entry['identity']['alarm_key']
        if name.startswith('m'):
            entry['visual_targets'][0]['process_projection_mode'] = 'DISTRIBUTED'
            entry['operational_areas'] = ['MINE']
        elif name.startswith('p'):
            entry['visual_targets'][0]['process_projection_mode'] = 'DISTRIBUTED'
            entry['operational_areas'] = ['PLANT']
    return configuration


def _view(destination) -> dict:
    return destination.read('current/latest.json')['tools']['tool-a']


def test_processor_rotates_normal_and_distributed_areas_independently(pipeline, monkeypatch):
    runner, runtime, current, destination = pipeline
    runner.rotation_seconds = CAROUSEL_ROTATION_SECONDS
    names = tuple(f'n{i}' for i in range(6)) + tuple(f'm{i}' for i in range(5)) + tuple(
        f'p{i}' for i in range(4)
    )
    monkeypatch.setattr(processor, 'modeler_to_document', lambda _: _configuration(names))
    now = [_at(0)]
    runner.clock = lambda: now[0]
    runtime.replace('runtime/state/effective-head.json', {'artifact_ref': REF})
    current.replace('current/latest.json', source([alarm(name) for name in names]))
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    first = _view(destination)
    first_mine = first['meta']['queue_in_queue']['visible_by_area']['MINE']
    assert first_mine == ['occ-m0', 'occ-m1', 'occ-m2']
    assert len(first['operator_view']) == 6

    now[0] = _at(60)
    assert runner.run_iteration(Context()).status == 'SKIPPED'
    assert _view(destination) == first

    now[0] = _at(90)
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    second = _view(destination)
    assert second['operator_view'][:5] != first['operator_view'][:5]
    assert second['meta']['queue_in_queue']['visible_by_area']['MINE'] == first_mine

    now[0] = _at(120)
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    third = _view(destination)
    assert third['meta']['queue_in_queue']['visible_by_area']['MINE'] == [
        'occ-m3', 'occ-m4', 'occ-m0'
    ]
    assert third['operator_view'][:5] == second['operator_view'][:5]


def test_distributed_rotation_survives_restart(pipeline, monkeypatch):
    runner, runtime, current, destination = pipeline
    names = tuple(f'm{i}' for i in range(5)) + ('p0', 'p1')
    monkeypatch.setattr(processor, 'modeler_to_document', lambda _: _configuration(names))
    runner.clock = lambda: _at(0)
    runtime.replace('runtime/state/effective-head.json', {'artifact_ref': REF})
    current.replace('current/latest.json', source([alarm(name) for name in names]))
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    previous = _view(destination)
    restarted = processor.AlarmModelerProcessor(
        runtime_root=runner.runtime_root,
        output_root=runner.output_root,
        rotation_seconds=runner.rotation_seconds,
        max_visible_slots=runner.max_visible_slots,
        clock=lambda: _at(120),
    )
    assert restarted.run_iteration(Context()).status == 'PUBLISHED'
    changed = _view(destination)
    assert changed['meta']['queue_in_queue'] != previous['meta']['queue_in_queue']
    memory = ToolRotationMemory(runner.output_root)
    assert memory.read(tool_key='tool-a', previous_tool=changed) is not None
