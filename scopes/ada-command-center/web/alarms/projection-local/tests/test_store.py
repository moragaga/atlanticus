import json
from datetime import UTC, datetime

import pytest

from ada_command_center.domain.alarms import AlarmConfiguration, AlarmConfigurationSnapshot
from ada_command_center.domain.tools import ToolDependencyManifest
from ada_command_center.web.alarms.configuration.errors import AlarmConfigurationProjectionError
from ada_command_center.web.alarms.projection.local import (
    LocalAlarmConfigurationProjectionStore,
    LocalAlarmConfigurationProjectionStoreSettings,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId


def _record(release: str = 'alarm-r1') -> ProjectionRecord[AlarmConfigurationSnapshot]:
    return ProjectionRecord(
        source_key=SourceKey('alarm-configuration'),
        source_release_id=SourceReleaseId(release),
        source_published_at_utc=datetime(2026, 9, 22, 10, tzinfo=UTC),
        projected_at_utc=datetime(2026, 9, 22, 10, 1, tzinfo=UTC),
        payload=AlarmConfigurationSnapshot(
            configuration=AlarmConfiguration(rules=(), messages=()),
            tool_dependencies=ToolDependencyManifest(
                confirmed_tool_catalog_revision='tools-r1', tools=()
            ),
        ),
    )


def test_local_projection_survives_restart(tmp_path) -> None:
    settings = LocalAlarmConfigurationProjectionStoreSettings(root=tmp_path)
    record = _record()
    LocalAlarmConfigurationProjectionStore(settings).replace_active(record)
    loaded = LocalAlarmConfigurationProjectionStore(settings).get_active(record.source_key)
    assert loaded == record
    assert loaded.target == record.target


def test_local_projection_replaces_active_head_without_creating_history(tmp_path) -> None:
    store = LocalAlarmConfigurationProjectionStore(
        LocalAlarmConfigurationProjectionStoreSettings(root=tmp_path)
    )
    store.replace_active(_record('r1'))
    store.replace_active(_record('r2'))
    assert store.get_active(SourceKey('alarm-configuration')) == _record('r2')
    assert len(list(tmp_path.glob('alarm_configuration_projection_*.json'))) == 1


def test_local_projection_rejects_corrupted_document(tmp_path) -> None:
    store = LocalAlarmConfigurationProjectionStore(
        LocalAlarmConfigurationProjectionStoreSettings(root=tmp_path)
    )
    store.replace_active(_record())
    for file in tmp_path.glob('*.json'):
        file.write_text('{', encoding='utf-8')
    with pytest.raises(AlarmConfigurationProjectionError):
        store.get_active(SourceKey('alarm-configuration'))


def test_local_projection_rejects_wrong_source_key_in_saved_document(tmp_path) -> None:
    store = LocalAlarmConfigurationProjectionStore(
        LocalAlarmConfigurationProjectionStoreSettings(root=tmp_path)
    )
    store.replace_active(_record())
    (path,) = tuple(tmp_path.glob('*.json'))
    document = json.loads(path.read_text(encoding='utf-8'))
    document['source_key'] = 'other-source'
    path.write_text(json.dumps(document), encoding='utf-8')
    with pytest.raises(AlarmConfigurationProjectionError, match='source key'):
        store.get_active(SourceKey('alarm-configuration'))
