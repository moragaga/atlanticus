import json
from pathlib import Path

import pytest

from ada.alarms.materialization import AlarmResolutionStatus
from ada.alarms.persistence import (
    AlarmMaterializationPersistenceError,
    LocalAlarmMaterializationStore,
    materialization_root,
)

from .support import blocked_resolution, provenance, ready_resolution


def test_ready_publication_is_atomic_complete_and_readable(tmp_path: Path) -> None:
    root = materialization_root(tmp_path)
    store = LocalAlarmMaterializationStore(root=root)
    result = store.publish(
        source_key='alarm_configuration',
        provenance=provenance(),
        resolution=ready_resolution(),
    )
    assert result.status is AlarmResolutionStatus.READY
    assert result.promoted_ready is True
    version = root / 'versions' / result.result_id
    assert {path.name for path in version.iterdir()} == {
        'manifest.json',
        'engine.json',
        'modeler.json',
        'delivery.json',
    }
    ready = store.read_published_ready(source_key='alarm_configuration')
    assert ready is not None
    assert ready.result_id == result.result_id
    assert ready.engine.resolution_key == ready.modeler.resolution_key
    assert ready.modeler.resolution_key == ready.delivery.resolution_key
    assert ready.manifest_sha256 == result.manifest_sha256


def test_narrow_readers_return_only_owned_ready_configuration(tmp_path: Path) -> None:
    store = LocalAlarmMaterializationStore(root=materialization_root(tmp_path))
    resolution = ready_resolution()
    store.publish(
        source_key='alarm_configuration',
        provenance=provenance(),
        resolution=resolution,
    )
    assert (
        store.read_published_engine(source_key='alarm_configuration')
        == resolution.engine_configuration
    )
    assert (
        store.read_published_modeler(source_key='alarm_configuration')
        == resolution.modeler_configuration
    )
    assert (
        store.read_published_delivery(source_key='alarm_configuration')
        == resolution.delivery_configuration
    )


def test_narrow_readers_return_none_without_published_ready(tmp_path: Path) -> None:
    store = LocalAlarmMaterializationStore(root=materialization_root(tmp_path))
    assert store.read_published_engine(source_key='alarm_configuration') is None
    assert store.read_published_modeler(source_key='alarm_configuration') is None
    assert store.read_published_delivery(source_key='alarm_configuration') is None


def test_engine_reader_does_not_deserialize_unowned_artifacts(tmp_path: Path) -> None:
    root = materialization_root(tmp_path)
    store = LocalAlarmMaterializationStore(root=root)
    resolution = ready_resolution()
    result = store.publish(
        source_key='alarm_configuration',
        provenance=provenance(),
        resolution=resolution,
    )
    modeler_path = root / 'versions' / result.result_id / 'modeler.json'
    modeler_path.write_text('{}', encoding='utf-8')
    assert (
        store.read_published_engine(source_key='alarm_configuration')
        == resolution.engine_configuration
    )


def test_narrow_reader_detects_owned_artifact_tampering(tmp_path: Path) -> None:
    root = materialization_root(tmp_path)
    store = LocalAlarmMaterializationStore(root=root)
    result = store.publish(
        source_key='alarm_configuration',
        provenance=provenance(),
        resolution=ready_resolution(),
    )
    engine_path = root / 'versions' / result.result_id / 'engine.json'
    document = json.loads(engine_path.read_text(encoding='utf-8'))
    document['defined_alarm_identities'] = []
    engine_path.write_text(json.dumps(document), encoding='utf-8')
    with pytest.raises(AlarmMaterializationPersistenceError, match='integrity check failed'):
        store.read_published_engine(source_key='alarm_configuration')


def test_blocked_publication_does_not_replace_last_ready(tmp_path: Path) -> None:
    root = materialization_root(tmp_path)
    store = LocalAlarmMaterializationStore(root=root)
    ready_resolution_value = ready_resolution()
    ready_result = store.publish(
        source_key='alarm_configuration',
        provenance=provenance(),
        resolution=ready_resolution_value,
    )
    blocked_result = store.publish(
        source_key='alarm_configuration',
        provenance=provenance(
            release='ALARMS-8',
            projection_digest='c' * 64,
            qualification_digest='d' * 64,
        ),
        resolution=blocked_resolution(),
    )
    assert blocked_result.status is AlarmResolutionStatus.BLOCKED
    assert blocked_result.promoted_ready is False
    blocked_version = root / 'versions' / blocked_result.result_id
    assert {path.name for path in blocked_version.iterdir()} == {'manifest.json'}
    published = store.read_published_ready(source_key='alarm_configuration')
    assert published is not None
    assert published.result_id == ready_result.result_id
    assert (
        store.read_published_engine(source_key='alarm_configuration')
        == ready_resolution_value.engine_configuration
    )
    assert (
        store.read_published_modeler(source_key='alarm_configuration')
        == ready_resolution_value.modeler_configuration
    )
    assert (
        store.read_published_delivery(source_key='alarm_configuration')
        == ready_resolution_value.delivery_configuration
    )


def test_repeat_ready_publication_is_idempotent(tmp_path: Path) -> None:
    store = LocalAlarmMaterializationStore(root=materialization_root(tmp_path))
    first = store.publish(
        source_key='alarm_configuration',
        provenance=provenance(),
        resolution=ready_resolution(),
    )
    second = store.publish(
        source_key='alarm_configuration',
        provenance=provenance(),
        resolution=ready_resolution(),
    )
    assert second.result_id == first.result_id
    assert second.manifest_sha256 == first.manifest_sha256
    assert second.promoted_ready is False


def test_ready_reader_detects_artifact_tampering(tmp_path: Path) -> None:
    root = materialization_root(tmp_path)
    store = LocalAlarmMaterializationStore(root=root)
    result = store.publish(
        source_key='alarm_configuration',
        provenance=provenance(),
        resolution=ready_resolution(),
    )
    engine_path = root / 'versions' / result.result_id / 'engine.json'
    document = json.loads(engine_path.read_text(encoding='utf-8'))
    document['defined_alarm_identities'] = []
    engine_path.write_text(json.dumps(document), encoding='utf-8')
    with pytest.raises(AlarmMaterializationPersistenceError, match='integrity check failed'):
        store.read_ready(
            source_key='alarm_configuration',
            result_id=result.result_id,
        )


def test_ready_reader_rejects_extra_files_in_published_version(tmp_path: Path) -> None:
    root = materialization_root(tmp_path)
    store = LocalAlarmMaterializationStore(root=root)
    result = store.publish(
        source_key='alarm_configuration',
        provenance=provenance(),
        resolution=ready_resolution(),
    )
    version = root / 'versions' / result.result_id
    (version / 'extra.json').write_text('{}', encoding='utf-8')
    with pytest.raises(AlarmMaterializationPersistenceError, match='invalid file inventory'):
        store.read_ready(
            source_key='alarm_configuration',
            result_id=result.result_id,
        )


def test_materialization_root_uses_explicit_application_root(tmp_path: Path) -> None:
    first = materialization_root(tmp_path / 'engine-a')
    second = materialization_root(tmp_path / 'engine-b')

    assert first == tmp_path / 'engine-a' / 'alarms' / 'materialization'
    assert second == tmp_path / 'engine-b' / 'alarms' / 'materialization'
    assert first != second
