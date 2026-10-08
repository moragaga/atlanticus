from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.contracts.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada.contracts.alarms import AlarmConfiguration, AlarmConfigurationSnapshot
from ada.contracts.tools import ToolDependencyManifest
from ada_command_center.web.alarms.configuration.source_release import (
    AlarmConfigurationSourceService,
)
from ada_command_center.web.application.configuration_manager import ALARM_CONFIGURATION_SOURCE_KEY
from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    ManagerConfigurationReader,
)
from ada_command_center.web.application.configuration_manager.local_runtime import (
    open_local_configuration_manager,
)
from ada_command_center.web.tools.catalog import (
    BlobToolCatalogStore,
    BlobToolCatalogStoreSettings,
    ToolCatalogEntry,
    create_tool_catalog_snapshot,
)
from atlanticus.connectivity.storage import StorageBlobNotFoundError, StorageClient
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.source.models import SourceReleaseId


class StorageStub(StorageClient):
    def __init__(self, *, settings, blobs):
        self.settings = settings
        self.blobs = blobs
        self.closed = False

    def download(self, *, container_name, blob_name):
        try:
            return self.blobs[(container_name, blob_name)]
        except KeyError:
            raise StorageBlobNotFoundError('Not found') from None

    def upload(self, *, container_name, blob_name, data, **_kwargs):
        self.blobs[(container_name, blob_name)] = bytes(data)

    def close(self):
        self.closed = True


def _reader(tmp_path, *, environment='local'):
    return ManagerConfigurationReader(
        root=tmp_path,
        environ_supplier=lambda: {
            'ATLANTICUS_ENVIRONMENT': environment,
            'ADA_MANAGER_PERSISTENCE_PROVIDER': 'local',
            'ADA_APPLICATION_NAMESPACE': 'conciencia_situacional',
            'ADA_TOOL_NAMESPACE': 'command-center',
            'ADA_COMMAND_CENTER_STORAGE_CONNECTION_STRING': 'UseDevelopmentStorage=true',
            'ADA_COMMAND_CENTER_STORAGE_CONTAINER_NAME': 'configurations',
        },
    )


def _storage(monkeypatch):
    from ada_command_center.web.application.configuration_manager import local_runtime

    blobs = {}
    instances = []

    def factory(*, settings):
        storage = StorageStub(settings=settings, blobs=blobs)
        instances.append(storage)
        return storage

    monkeypatch.setattr(local_runtime, 'StorageClient', factory)
    return blobs, instances


def _principal():
    return ManagerPrincipal(
        subject_id='local',
        display_name='Administrador local',
        profile_keys=('local',),
        access_keys=(),
        administrative_override=True,
        is_local=True,
    )


def _manual_catalog():
    structure = ToolStructure(
        tool_key='mine_tool',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.PLANT,
        center_component_key='process',
        components=(
            ToolComponent(
                key='process',
                display_name='Process',
                subcomponents=(ToolSubcomponent(key='line', display_name='Line'),),
            ),
        ),
    )
    return create_tool_catalog_snapshot(
        (
            ToolCatalogEntry(
                tool_key='mine_tool',
                display_name='Mine Tool',
                kind=ToolConfigurationKind.PROCESS,
                source_release_id=SourceReleaseId('manual-release'),
                structure=structure,
            ),
        ),
        generated_at_utc=datetime(2026, 9, 29, tzinfo=UTC),
    )


def _manual_alarm_release(dependencies, revision):
    source = AlarmConfigurationSourceService(
        source=dependencies.source_store,
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
    )
    observed = source.get_current()
    snapshot = AlarmConfigurationSnapshot(
        configuration=AlarmConfiguration(rules=(), messages=()),
        tool_dependencies=ToolDependencyManifest(
            confirmed_tool_catalog_revision=revision,
            tools=(),
        ),
    )
    source.publish_snapshot(
        snapshot,
        published_by='manual-test',
        expected_concurrency_token=observed.concurrency_token,
        basis_release=observed.current.release_ref if observed.current else None,
    )
    return snapshot


def test_local_starts_empty_without_examples_and_closes_storage(tmp_path, monkeypatch) -> None:
    blobs, clients = _storage(monkeypatch)
    with open_local_configuration_manager(
        reader=_reader(tmp_path),
        principal_provider=_principal,
        base_root=tmp_path,
    ) as dependencies:
        assert dependencies.tool_reference_reader.load() is None
        assert dependencies.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY) is None
        source = AlarmConfigurationSourceService(
            source=dependencies.source_store,
            source_key=ALARM_CONFIGURATION_SOURCE_KEY,
        )
        assert source.load_current() is None
        assert dependencies.tool_catalog_manager is not None
        principal = dependencies.principal_provider()
        assert principal.profile_keys == ('local',)
        assert principal.access_keys == ()
        assert principal.administrative_override is True
        assert principal.is_local is True
    assert not blobs
    assert len(clients) == 1 and clients[0].closed


def test_manually_confirmed_catalog_is_the_only_local_tool_source(tmp_path, monkeypatch) -> None:
    _blobs, clients = _storage(monkeypatch)
    with open_local_configuration_manager(
        reader=_reader(tmp_path),
        principal_provider=_principal,
        base_root=tmp_path,
    ) as dependencies:
        store = BlobToolCatalogStore(
            storage=clients[-1],
            settings=BlobToolCatalogStoreSettings(
                container_name='configurations',
                blob_name=_reader(tmp_path).namespace.scope_blob_name('tool-catalog/current.json'),
            ),
        )
        snapshot = _manual_catalog()
        store.replace_current(snapshot)
        loaded = dependencies.tool_reference_reader.load()
        assert loaded is not None
        assert loaded.catalog_revision == snapshot.revision
        assert tuple(tool.tool_key for tool in loaded.tools) == ('mine_tool',)
        source = AlarmConfigurationSourceService(
            source=dependencies.source_store,
            source_key=ALARM_CONFIGURATION_SOURCE_KEY,
        )
        assert source.load_current() is None
        _manual_alarm_release(dependencies, snapshot.revision)
        assert dependencies.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY) is None
    with open_local_configuration_manager(
        reader=_reader(tmp_path),
        principal_provider=_principal,
        base_root=tmp_path,
    ) as restarted:
        assert restarted.tool_reference_reader.load().catalog_revision == snapshot.revision
        source = AlarmConfigurationSourceService(
            source=restarted.source_store,
            source_key=ALARM_CONFIGURATION_SOURCE_KEY,
        )
        assert source.load_current() is not None
        assert restarted.projection_store.get_active(ALARM_CONFIGURATION_SOURCE_KEY) is None
    assert (tmp_path / 'conciencia_situacional' / 'command-center').exists()


def test_local_provider_rejects_production_even_with_storage_configuration(
    tmp_path, monkeypatch
) -> None:
    _storage(monkeypatch)
    with (
        pytest.raises(ValueError, match='local Web environment'),
        open_local_configuration_manager(
            reader=_reader(tmp_path, environment='production'),
            principal_provider=_principal,
            base_root=tmp_path,
        ),
    ):
        pass
