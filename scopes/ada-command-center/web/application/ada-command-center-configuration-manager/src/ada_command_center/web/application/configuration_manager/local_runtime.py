from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from ada_command_center.web.alarms.configuration.resources import (
    ALARM_CONFIGURATION_PROJECTION_PHYSICAL_NAME,
)
from ada_command_center.web.alarms.configuration.tool_references import AlarmToolReferenceReader
from ada_command_center.web.alarms.persistence import (
    AlarmConfigurationPersistenceSettings,
    AlarmConfigurationProjectionProvider,
    AlarmConfigurationSourceProvider,
    compose_alarm_configuration_persistence,
)
from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    COMMAND_CENTER_CATALOG_BLOB_NAME,
    COMMAND_CENTER_NAMESPACE,
    STORAGE_CONTAINER_VARIABLE,
    ManagerConfigurationReader,
    catalog_storage_settings,
)
from ada_command_center.web.application.configuration_manager.dependencies import (
    ConfigurationManagerDependencies,
)
from ada_command_center.web.tools.catalog import BlobToolCatalogStore, BlobToolCatalogStoreSettings
from ada_command_center.web.tools.discovery_cosmos.manager import ToolCatalogManagerService
from atlanticus.connectivity.storage import StorageClient
from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.manager import ManagerPrincipal


@contextmanager
def open_local_configuration_manager(
    *,
    reader: ManagerConfigurationReader,
    principal_provider: Callable[[], ManagerPrincipal],
    base_root: Path | None = None,
) -> Iterator[ConfigurationManagerDependencies]:
    if reader.environment is not WebEnvironment.LOCAL:
        raise ValueError('Local Manager requires local Web environment')
    if reader.manager_provider != 'local':
        raise ValueError('Local Manager requires local provider')
    if not callable(principal_provider):
        raise TypeError('principal_provider must be callable')
    values = reader.storage()
    root = (base_root if base_root is not None else Path.cwd() / '.runtime').expanduser()
    if not root.is_absolute():
        raise ValueError('Local Manager base root must be absolute')
    namespace = COMMAND_CENTER_NAMESPACE
    persistence = compose_alarm_configuration_persistence(
        settings=AlarmConfigurationPersistenceSettings(
            source_provider=AlarmConfigurationSourceProvider.LOCAL,
            projection_provider=AlarmConfigurationProjectionProvider.LOCAL,
            local_source_root=namespace.local_tool_root(root),
            local_projection_root=(
                namespace.local_projection_root(root)
                / ALARM_CONFIGURATION_PROJECTION_PHYSICAL_NAME
            ),
        ),
    )
    with ExitStack() as stack:
        storage = StorageClient(settings=catalog_storage_settings(values))
        stack.callback(storage.close)
        catalog = BlobToolCatalogStore(
            storage=storage,
            settings=BlobToolCatalogStoreSettings(
                container_name=values[STORAGE_CONTAINER_VARIABLE],
                blob_name=COMMAND_CENTER_CATALOG_BLOB_NAME,
            ),
        )
        yield ConfigurationManagerDependencies(
            source_store=persistence.source,
            projection_store=persistence.projection,
            principal_provider=principal_provider,
            tool_reference_reader=AlarmToolReferenceReader(store=catalog),
            tool_catalog_manager=ToolCatalogManagerService(
                catalog=catalog,
                connection_provider=reader.external,
            ),
            source_name='Local Source',
            projection_name='Local Projection',
        )
