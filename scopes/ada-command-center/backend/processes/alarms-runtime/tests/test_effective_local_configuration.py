from __future__ import annotations

import json
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Iterator

import pytest

from ada_command_center.alarms.materialization.local_reader import (
    AlarmMaterializationPublicationError,
    materialization_result_id,
    materialization_root,
)
from ada_command_center.alarms.persistence import (
    GROUP_RUNTIME_SNAPSHOT_SCHEMA_VERSION,
    AlarmArtifactRefSnapshot,
    AlarmPersistence,
    AlarmPersistenceCorruptionError,
    AlarmRecoveryRequiredError,
    ConfigurationAdoptionRecord,
    ConfigurationAdoptionRecordV2,
    EngineCommitMetadata,
    EngineCommitRecord,
    GroupCommitReference,
    GroupRuntimeSnapshot,
)
from ada_command_center.processes.alarms_runtime import (
    AlarmEvaluatorRegistry,
    RuntimeEffectiveConfiguration,
    RuntimeEffectiveConfigurationError,
    RuntimeLocalConfigurationReader,
)

SOURCE = 'alarm-configuration'
WHEN = '2026-09-27T20:00:00Z'


def _write(path: Path, document: dict) -> tuple[str, int]:
    content = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(',', ':')
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return sha256(content).hexdigest(), len(content)


def _publish(
    volume: Path,
    *,
    release: str = 'R42',
    tool: str = 'T18',
    qualification: str = 'b' * 64,
    promote: bool = True,
) -> tuple[Path, AlarmArtifactRefSnapshot]:
    root = materialization_root(volume)
    digest = 'a' * 64
    result_id = materialization_result_id(
        source_key=SOURCE, projection_digest=digest, qualification_digest=qualification
    )
    resolution = {
        'alarm_configuration_revision': release,
        'confirmed_tool_catalog_revision': tool,
    }
    version = root / 'versions' / result_id
    runtime = {
        'resolution_key': resolution,
        'defined_alarm_identities': [],
        'planned_alarms': [],
        'parameters_by_alarm': [],
    }
    delivery = {'resolution_key': resolution, 'alarms': []}
    inventory = {}
    for label, value in (('runtime', runtime), ('delivery', delivery)):
        digest_for_file, size = _write(version / f'{label}.json', value)
        inventory[label] = {
            'path': f'{label}.json',
            'sha256': digest_for_file,
            'size_bytes': size,
        }
    manifest = {
        'document_type': 'ada_command_center_alarm_materialization_result',
        'schema_version': 1,
        'source_key': SOURCE,
        'result_id': result_id,
        'status': 'READY',
        'resolution_key': resolution,
        'provenance': {
            'source_release_id': release,
            'source_published_at_utc': '2026-09-26T12:00:00+00:00',
            'confirmed_tool_catalog_revision': tool,
            'projection_digest': digest,
            'qualification_digest': qualification,
            'qualification_producer': 'controlled-test',
            'qualification_evidence_ref': 'qualification-1',
            'qualified_at_utc': '2026-09-26T12:01:00+00:00',
        },
        'findings': [],
        'artifacts': inventory,
    }
    manifest_hash, _ = _write(version / 'manifest.json', manifest)
    if promote:
        _write(
            root / 'ready.json',
            {
                'document_type': 'ada_command_center_alarm_materialization_ready',
                'schema_version': 1,
                'source_key': SOURCE,
                'result_id': result_id,
                'resolution_key': resolution,
                'manifest_sha256': manifest_hash,
            },
        )
    return version, AlarmArtifactRefSnapshot(
        source_key=SOURCE,
        result_id=result_id,
        manifest_sha256=manifest_hash,
        alarm_configuration_revision=release,
        confirmed_tool_catalog_revision=tool,
    )


@contextmanager
def _mutation() -> Iterator[None]:
    yield


def _authority() -> None:
    return None


def _adopt(
    persistence: AlarmPersistence,
    target: AlarmArtifactRefSnapshot,
    *,
    previous: AlarmArtifactRefSnapshot | None = None,
    adoption_id: str = 'adoption-1',
) -> None:
    persistence.commit_adoption(
        ConfigurationAdoptionRecord.create(
            adoption_id=adoption_id,
            previous_artifact_ref=previous,
            target_artifact_ref=target,
            effective_at=WHEN,
            committed_at=WHEN,
        ),
        assert_authority=_authority,
        fenced_mutation=_mutation,
    )


def _reader(volume: Path, source: str = SOURCE) -> RuntimeLocalConfigurationReader:
    return RuntimeLocalConfigurationReader(volume_path=volume, source_key=source)


def _selected(reader: RuntimeLocalConfigurationReader, persistence: AlarmPersistence):
    return reader.load_effective_revision(
        persistence=persistence, evaluator_registry=AlarmEvaluatorRegistry(contracts=())
    )


def test_ready_without_durable_adoption_is_not_effective(tmp_path: Path) -> None:
    _, pin = _publish(tmp_path)
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    assert _reader(tmp_path).load_ready_candidate().result_id == pin.result_id
    assert _selected(_reader(tmp_path), persistence) is None


def test_v1_reads_exact_effective_even_when_latest_ready_is_different(tmp_path: Path) -> None:
    _, first = _publish(tmp_path)
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _adopt(persistence, first)
    _, latest = _publish(tmp_path, release='R43', qualification='c' * 64)
    reader = _reader(tmp_path)
    selected = _selected(reader, persistence)
    assert isinstance(selected, RuntimeEffectiveConfiguration)
    assert selected.revision.artifact_ref.result_id == first.result_id
    assert selected.revision.alarm_configuration_revision == 'R42'
    assert reader.load_ready_candidate().result_id == latest.result_id
    assert selected.effective_head == persistence.read_effective_head()
    reader.assert_current_effective(persistence=persistence, selected=selected)


def test_distinct_exact_materialization_same_revisions_does_not_replace_effective(
    tmp_path: Path,
) -> None:
    _, first = _publish(tmp_path)
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _adopt(persistence, first)
    _, second = _publish(tmp_path, qualification='d' * 64)
    assert second.result_id != first.result_id
    assert second.alarm_configuration_revision == first.alarm_configuration_revision
    assert (
        _selected(_reader(tmp_path), persistence).revision.artifact_ref.result_id == first.result_id
    )


def _group_record(group: str) -> EngineCommitRecord:
    commit_id = f'{group}-commit'
    metadata = EngineCommitMetadata(
        commit_id=commit_id,
        cycle_id='20260927T200000000000Z',
        priority_group=group,
        previous_commit_id=None,
        evaluated_at=WHEN,
        committed_at=WHEN,
        alarm_configuration_revision='R42',
        tool_registry_revision='T18',
        runtime_artifact_version='alarms-runtime/1',
        affected_alarms=(f'alarm-{group}',),
    )
    snapshot = GroupRuntimeSnapshot(
        {
            'snapshot_schema_version': GROUP_RUNTIME_SNAPSHOT_SCHEMA_VERSION,
            'priority_group': group,
            'last_commit_id': commit_id,
            'state_basis': {
                'alarm_configuration_revision': 'R42',
                'tool_registry_revision': 'T18',
            },
            'alarms': {},
        }
    )
    return EngineCommitRecord.create(commit=metadata, snapshot_after=snapshot, records={})


def test_v2_reads_exact_effective_only_after_group_transaction(tmp_path: Path) -> None:
    _, pin = _publish(tmp_path)
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    groups = (_group_record('alpha'), _group_record('beta'))
    record = ConfigurationAdoptionRecordV2.create(
        adoption_id='adoption-v2',
        previous_artifact_ref=None,
        target_artifact_ref=pin,
        effective_at=WHEN,
        committed_at=WHEN,
        group_commits=tuple(
            GroupCommitReference(
                priority_group=item.commit.priority_group,
                commit_id=item.commit.commit_id,
                record_hash=item.record_hash,
            )
            for item in groups
        ),
    )
    persistence.commit_adoption(
        record, group_records=groups, assert_authority=_authority, fenced_mutation=_mutation
    )
    selected = _selected(_reader(tmp_path), persistence)
    assert selected.effective_head.adoption_id == 'adoption-v2'
    assert selected.revision.artifact_ref.result_id == pin.result_id
    assert len(persistence.read_durable_records()) == 2


def test_wrong_effective_source_rejects_without_falling_back_to_ready(tmp_path: Path) -> None:
    _, pin = _publish(tmp_path)
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _adopt(persistence, pin)
    with pytest.raises(RuntimeEffectiveConfigurationError, match='source_key'):
        _selected(_reader(tmp_path, source='another-source'), persistence)


def test_same_volume_is_required_for_effective_authority(tmp_path: Path) -> None:
    _publish(tmp_path)
    wrong = AlarmPersistence(shared_volume_path=tmp_path / 'other')
    with pytest.raises(ValueError, match='same VOLUMEN_PATH'):
        _selected(_reader(tmp_path), wrong)


def test_missing_exact_artifact_fails_without_fallback_to_new_ready(tmp_path: Path) -> None:
    first_dir, first = _publish(tmp_path)
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _adopt(persistence, first)
    _publish(tmp_path, release='R43', qualification='c' * 64)
    (first_dir / 'manifest.json').unlink()
    with pytest.raises(AlarmMaterializationPublicationError):
        _selected(_reader(tmp_path), persistence)


def test_corrupt_exact_artifact_does_not_fallback_to_ready(tmp_path: Path) -> None:
    first_dir, first = _publish(tmp_path)
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _adopt(persistence, first)
    _publish(tmp_path, release='R43', qualification='c' * 64)
    (first_dir / 'runtime.json').write_text('{"wrong": true}', encoding='utf-8')
    with pytest.raises(AlarmMaterializationPublicationError, match='integrity'):
        _selected(_reader(tmp_path), persistence)


def test_effective_resolution_mismatch_is_rejected(tmp_path: Path) -> None:
    _, pin = _publish(tmp_path)
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    wrong = AlarmArtifactRefSnapshot(
        source_key=pin.source_key,
        result_id=pin.result_id,
        manifest_sha256=pin.manifest_sha256,
        alarm_configuration_revision='R-other',
        confirmed_tool_catalog_revision=pin.confirmed_tool_catalog_revision,
    )
    _adopt(persistence, wrong)
    with pytest.raises(RuntimeEffectiveConfigurationError, match='exact EFFECTIVE'):
        _selected(_reader(tmp_path), persistence)


def test_unaligned_wal_blocks_effective_reader(tmp_path: Path, monkeypatch) -> None:
    _publish(tmp_path)
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _, pin = _publish(tmp_path)
    monkeypatch.setattr(
        persistence,
        '_materialize_entry',
        lambda entry: (_ for _ in ()).throw(RuntimeError('simulated crash')),
    )
    with pytest.raises(RuntimeError, match='simulated crash'):
        _adopt(persistence, pin)
    with pytest.raises(AlarmRecoveryRequiredError):
        _selected(_reader(tmp_path), persistence)


def test_missing_effective_projection_requires_recovery(tmp_path: Path) -> None:
    _, pin = _publish(tmp_path)
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _adopt(persistence, pin)
    (persistence.paths.alarms_root / persistence.paths.effective_head_relative).unlink()
    with pytest.raises(AlarmRecoveryRequiredError):
        _selected(_reader(tmp_path), persistence)
    persistence.recover(assert_authority=_authority, fenced_mutation=_mutation)
    assert (
        _selected(_reader(tmp_path), persistence).revision.artifact_ref.result_id == pin.result_id
    )


def test_corrupt_effective_projection_fails_closed(tmp_path: Path) -> None:
    _, pin = _publish(tmp_path)
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _adopt(persistence, pin)
    (persistence.paths.alarms_root / persistence.paths.effective_head_relative).write_text(
        '{"invalid": true}', encoding='utf-8'
    )
    with pytest.raises(AlarmPersistenceCorruptionError):
        _selected(_reader(tmp_path), persistence)


def test_change_during_exact_read_is_rejected(tmp_path: Path, monkeypatch) -> None:
    _, first = _publish(tmp_path)
    _, second = _publish(tmp_path, release='R43', qualification='c' * 64)
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _adopt(persistence, first)
    reader = _reader(tmp_path)
    original = RuntimeLocalConfigurationReader.load_exact_candidate

    def advance(self, *, result_id, manifest_sha256):
        _adopt(persistence, second, previous=first, adoption_id='adoption-2')
        return original(self, result_id=result_id, manifest_sha256=manifest_sha256)

    monkeypatch.setattr(RuntimeLocalConfigurationReader, 'load_exact_candidate', advance)
    with pytest.raises(RuntimeEffectiveConfigurationError, match='changed'):
        _selected(reader, persistence)


def test_later_adoption_invalidates_previous_selected_revision(tmp_path: Path) -> None:
    _, first = _publish(tmp_path)
    _, second = _publish(tmp_path, release='R43', qualification='c' * 64)
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    _adopt(persistence, first)
    reader = _reader(tmp_path)
    selected = _selected(reader, persistence)
    _adopt(persistence, second, previous=first, adoption_id='adoption-2')
    with pytest.raises(RuntimeEffectiveConfigurationError, match='changed'):
        reader.assert_current_effective(persistence=persistence, selected=selected)


def test_effective_reader_requires_real_registry(tmp_path: Path) -> None:
    persistence = AlarmPersistence(shared_volume_path=tmp_path)
    with pytest.raises(TypeError, match='evaluator_registry'):
        _reader(tmp_path).load_effective_revision(persistence=persistence, evaluator_registry=None)
