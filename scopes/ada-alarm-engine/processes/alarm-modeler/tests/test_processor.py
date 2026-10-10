from __future__ import annotations

from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from ada.processes.alarm_modeler import processor
from ada.processes.alarm_modeler.projection import AlarmModelerProjectionError
from atlanticus.state import AtomicJsonStore

from .test_projection import REF, alarm, model, source


class Context:
    def assert_lease_current(self):
        return None

    def fenced_mutation(self):
        return nullcontext()


class Ref:
    def __init__(self, document):
        self.value = document
        self.source_key = document['source_key']
        self.result_id = document['result_id']
        self.manifest_sha256 = document['manifest_sha256']

    def __eq__(self, other):
        return isinstance(other, Ref) and self.value == other.value

    @classmethod
    def from_document(cls, document):
        return cls(document)


class Effective:
    @classmethod
    def from_document(cls, document):
        return SimpleNamespace(target_artifact_ref=Ref(document['artifact_ref']))


class ReadyStore:
    reads = 0
    def __init__(self, root):
        assert root.is_absolute()

    def read_ready(self, *, source_key, result_id, expected_manifest_sha256):
        self.__class__.reads += 1
        assert source_key == REF['source_key']
        assert result_id == REF['result_id']
        assert expected_manifest_sha256 == REF['manifest_sha256']
        value = SimpleNamespace(resolution_key='R1T1')
        return SimpleNamespace(
            engine=value,
            modeler=value,
            delivery=SimpleNamespace(resolution_key='R1T1', publication_tool_keys=('tool-a',)),
        )


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    ReadyStore.reads = 0
    monkeypatch.setattr(processor, 'AlarmArtifactRefSnapshot', Ref)
    monkeypatch.setattr(processor, 'AlarmEffectiveConfigurationHead', Effective)
    monkeypatch.setattr(processor, 'LocalAlarmMaterializationStore', ReadyStore)
    monkeypatch.setattr(processor, 'modeler_to_document', lambda value: model('a'))
    root = tmp_path / 'producer'
    output = tmp_path / 'modeler' / 'alarms' / 'modeler' / 'output'
    runner = processor.AlarmModelerProcessor(
        runtime_root=root,
        output_root=output,
        rotation_seconds=30,
        max_visible_slots=6,
        clock=lambda: datetime(2026, 10, 10, 18, tzinfo=UTC),
    )
    runtime = AtomicJsonStore(root_path=root / 'alarms', max_document_bytes=None)
    current = AtomicJsonStore(root_path=root / 'alarms' / 'output', max_document_bytes=None)
    destination = AtomicJsonStore(root_path=output, max_document_bytes=None)
    return runner, runtime, current, destination


def test_missing_sources_wait_without_writing(pipeline):
    runner, runtime, current, destination = pipeline
    assert runner.run_iteration(Context()).status == 'WAITING_EFFECTIVE'
    runtime.replace('runtime/state/effective-head.json', {'artifact_ref': REF})
    assert runner.run_iteration(Context()).status == 'WAITING_CURRENT'
    assert destination.read('current/latest.json') is None


def test_publish_skip_management_and_normalization(pipeline):
    runner, runtime, current, destination = pipeline
    runtime.replace('runtime/state/effective-head.json', {'artifact_ref': REF})
    current.replace('current/latest.json', source([alarm('a')]))
    first = runner.run_iteration(Context())
    assert first.status == 'PUBLISHED'
    original = destination.read('current/latest.json')
    assert original['tools']['tool-a']['operator_pool'] == ['occ-a']
    assert runner.run_iteration(Context()).status == 'SKIPPED'
    assert ReadyStore.reads == 1
    assert destination.read('current/latest.json') == original
    current.replace('current/latest.json', source([alarm('a', managed=True)]))
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    managed = destination.read('current/latest.json')['tools']['tool-a']
    assert 'occ-a' in managed['alarms']
    assert managed['operator_pool'] == []
    current.replace('current/latest.json', source([]))
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    assert destination.read('current/latest.json')['tools']['tool-a']['alarms'] == {}
    assert runner.run_iteration(Context()).status == 'SKIPPED'


def test_corrupt_existing_projection_blocks_overwrite(pipeline):
    runner, runtime, current, destination = pipeline
    runtime.replace('runtime/state/effective-head.json', {'artifact_ref': REF})
    current.replace('current/latest.json', source([alarm('a')]))
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    document = destination.read('current/latest.json')
    document['tools']['tool-a']['operator_pool'] = ['fake']
    destination.replace('current/latest.json', document)
    with pytest.raises(AlarmModelerProjectionError, match='checksum'):
        runner.run_iteration(Context())


def test_current_change_during_publish_is_retried(pipeline):
    runner, runtime, current, destination = pipeline
    runtime.replace('runtime/state/effective-head.json', {'artifact_ref': REF})
    current.replace('current/latest.json', source([alarm('a')]))

    class MutatingContext(Context):
        @contextmanager
        def fenced_mutation(self):
            current.replace('current/latest.json', source([alarm('a', managed=True)]))
            yield

    assert runner.run_iteration(MutatingContext()).status == 'SOURCE_CHANGED'
    assert destination.read('current/latest.json') is None
    assert runner.run_iteration(Context()).status == 'PUBLISHED'


def test_rotation_reprojects_when_current_is_identical(pipeline, monkeypatch):
    runner, runtime, current, destination = pipeline
    clock = [datetime.fromtimestamp(0, tz=UTC)]
    runner.clock = lambda: clock[0]
    runner.max_visible_slots = 3
    names = [f'a{i}' for i in range(7)]
    monkeypatch.setattr(processor, 'modeler_to_document', lambda value: model(*names))
    runtime.replace('runtime/state/effective-head.json', {'artifact_ref': REF})
    current.replace('current/latest.json', source([alarm(name) for name in names]))
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    original = destination.read('current/latest.json')['tools']['tool-a']['operator_view']
    clock[0] = datetime.fromtimestamp(10, tz=UTC)
    assert runner.run_iteration(Context()).status == 'SKIPPED'
    assert ReadyStore.reads == 1
    clock[0] = datetime.fromtimestamp(30, tz=UTC)
    assert runner.run_iteration(Context()).status == 'PUBLISHED'
    latest = destination.read('current/latest.json')['tools']['tool-a']['operator_view']
    assert original != latest
    assert ReadyStore.reads == 2
