from datetime import UTC, datetime

import pytest

from ada_command_center.domain.alarms import AlarmConfiguration, AlarmConfigurationSnapshot
from ada_command_center.domain.tools import ToolDependencyManifest
from ada_command_center.web.alarms.configuration.errors import AlarmConfigurationProjectionError
from ada_command_center.web.alarms.projection.cosmos import (
    ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE,
    CosmosAlarmConfigurationProjectionStore,
    CosmosAlarmConfigurationProjectionStoreSettings,
)
from atlanticus.connectivity.cosmos import CosmosError
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId


class _CosmosClient:
    def __init__(self) -> None:
        self.items = {}
        self.fail_read = False
        self.fail_write = False

    def find_item(self, *, container_name, item_id, partition_key):
        if self.fail_read:
            raise CosmosError('read failed')
        value = self.items.get((container_name, item_id, partition_key))
        return dict(value) if value is not None else None

    def upsert_item(self, *, container_name, item):
        if self.fail_write:
            raise CosmosError('write failed')
        value = dict(item)
        self.items[(container_name, value['id'], value['partition_key'])] = value
        return value


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


def test_cosmos_projection_roundtrip_preserves_exact_release_and_tool_manifest() -> None:
    client = _CosmosClient()
    settings = CosmosAlarmConfigurationProjectionStoreSettings(container_name='alarms')
    store = CosmosAlarmConfigurationProjectionStore(client=client, settings=settings)
    record = _record()
    assert store.replace_active(record) == record
    assert store.get_active(record.source_key) == record
    assert len(client.items) == 1
    stored = next(iter(client.items.values()))
    assert stored['partition_key'] == 'alarm-configuration'
    assert stored['payload']['tool_dependencies'] == record.payload.tool_dependencies.to_document()
    store.replace_active(_record('alarm-r2'))
    assert len(client.items) == 1
    assert store.get_active(record.source_key).source_release_id == SourceReleaseId('alarm-r2')


def test_cosmos_projection_distinguishes_absent_from_unavailable() -> None:
    client = _CosmosClient()
    store = CosmosAlarmConfigurationProjectionStore(
        client=client,
        settings=CosmosAlarmConfigurationProjectionStoreSettings(container_name='alarms'),
    )
    assert store.get_active(SourceKey('alarm-configuration')) is None
    client.fail_read = True
    with pytest.raises(AlarmConfigurationProjectionError):
        store.get_active(SourceKey('alarm-configuration'))
    client.fail_read = False
    client.fail_write = True
    with pytest.raises(AlarmConfigurationProjectionError):
        store.replace_active(_record())


def test_cosmos_projection_resource_contract() -> None:
    resource = ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE
    assert resource.logical_id == 'ada.command_center.alarms.configuration.projection'
    assert resource.owner == 'ada.command_center.alarms.configuration'
    assert resource.provider == 'cosmos'
    assert resource.default_physical_name == 'ada-command-center-alarm-configuration-projection'
    assert resource.topology.partition_key_path == '/partition_key'
    assert resource.topology.default_ttl_seconds is None


def test_failed_cosmos_replacement_leaves_previous_head_readable() -> None:
    client = _CosmosClient()
    store = CosmosAlarmConfigurationProjectionStore(
        client=client,
        settings=CosmosAlarmConfigurationProjectionStoreSettings(container_name='alarms'),
    )
    initial = _record('alarm-r1')
    store.replace_active(initial)
    client.fail_write = True
    with pytest.raises(AlarmConfigurationProjectionError):
        store.replace_active(_record('alarm-r2'))
    client.fail_write = False
    assert store.get_active(initial.source_key) == initial


def test_cosmos_projection_rejects_wrong_source_key_in_persisted_payload() -> None:
    client = _CosmosClient()
    store = CosmosAlarmConfigurationProjectionStore(
        client=client,
        settings=CosmosAlarmConfigurationProjectionStoreSettings(container_name='alarms'),
    )
    record = _record()
    store.replace_active(record)
    stored = next(iter(client.items.values()))
    stored['source_key'] = 'other-source'
    with pytest.raises(AlarmConfigurationProjectionError, match='source key'):
        store.get_active(record.source_key)
