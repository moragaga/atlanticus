# Espejo pedagógico equivalente al código productivo.
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass

from ada.web.storage.namespace import AdaStorageNamespace
from ada_command_center.tools.catalog import BlobToolCatalogStore, BlobToolCatalogStoreSettings
from ada_command_center.tools.discovery_cosmos.manager import ToolCatalogManagerService
from ada_command_center.web.alarms.configuration.tool_references import AlarmToolReferenceReader
from ada_command_center.web.alarms.persistence import (
    AlarmConfigurationPersistenceSettings,
    AlarmConfigurationProjectionProvider,
    AlarmConfigurationSourceProvider,
    compose_alarm_configuration_persistence,
)
from ada_command_center.web.alarms.projection.cosmos.storage import (
    ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE,
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
from atlanticus.connectivity.cosmos import CosmosClient, CosmosSettings
from atlanticus.connectivity.storage import StorageClient, StorageSettings
from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.storage.topology import StorageResourceOverride, resolve_storage_plan

_COSMOS_CONNECTION_REF = 'command-center-cosmos'


@dataclass(frozen=True, slots=True)
class CommandCenterDurableConfiguration:
    namespace: AdaStorageNamespace
    storage_settings: StorageSettings
    cosmos_settings: CosmosSettings
    storage_container_name: str
    catalog_blob_name: str
    alarm_source_root_prefix: str
    alarm_projection_container_name: str


def _require(values: Mapping[str, str], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f'Command Center configuration is missing or invalid: {name}')
    return value


# Reutiliza el namespace y la definición Cosmos propios del dominio.
def resolve_durable_configuration(
    values: Mapping[str, str], *, local: bool
) -> CommandCenterDurableConfiguration:
    namespace = COMMAND_CENTER_NAMESPACE
    plan = resolve_storage_plan(
        (ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE,),
        (
            StorageResourceOverride(
                logical_id=ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE.logical_id,
                connection_ref=_COSMOS_CONNECTION_REF,
            ),
        ),
    )
    projection = plan.resources[0]
    if projection.topology != ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE.topology:
        raise ValueError('Command Center projection topology is inconsistent')
    return CommandCenterDurableConfiguration(
        namespace=namespace,
        storage_settings=catalog_storage_settings(values),
        cosmos_settings=CosmosSettings(
            endpoint=_require(values, 'ADA_COMMAND_CENTER_COSMOS_ENDPOINT'),
            database_name=_require(values, 'ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME'),
            key=_require(values, 'ADA_COMMAND_CENTER_COSMOS_KEY'),
            allow_insecure_http=local,
        ),
        storage_container_name=_require(values, STORAGE_CONTAINER_VARIABLE),
        catalog_blob_name=COMMAND_CENTER_CATALOG_BLOB_NAME,
        alarm_source_root_prefix=namespace.tool_prefix,
        alarm_projection_container_name=projection.physical_name,
    )


@contextmanager
def open_durable_configuration_manager(
    *,
    reader: ManagerConfigurationReader,
    principal_provider: Callable[[], ManagerPrincipal],
    production_identity_bound: bool = False,
) -> Iterator[ConfigurationManagerDependencies]:
    if not callable(principal_provider):
        raise TypeError('principal_provider must be callable')
    if reader.environment == WebEnvironment.PRODUCTION and production_identity_bound is not True:
        raise ValueError('Production Command Center requires an authenticated host binding')
    if reader.manager_provider != 'durable':
        raise ValueError('Durable Manager requires durable provider')
    resolved = resolve_durable_configuration(
        reader.own(), local=reader.environment is WebEnvironment.LOCAL
    )
    # Los clientes son propiedad del host y se cierran al finalizar.
    with ExitStack() as stack:
        storage = StorageClient(settings=resolved.storage_settings)
        stack.callback(storage.close)
        cosmos = CosmosClient(settings=resolved.cosmos_settings)
        stack.callback(cosmos.close)
        catalog = BlobToolCatalogStore(
            storage=storage,
            settings=BlobToolCatalogStoreSettings(
                container_name=resolved.storage_container_name,
                blob_name=resolved.catalog_blob_name,
            ),
        )
        persistence = compose_alarm_configuration_persistence(
            settings=AlarmConfigurationPersistenceSettings(
                source_provider=AlarmConfigurationSourceProvider.BLOB,
                projection_provider=AlarmConfigurationProjectionProvider.COSMOS,
                blob_container_name=resolved.storage_container_name,
                blob_root_prefix=resolved.alarm_source_root_prefix,
                cosmos_container_name=resolved.alarm_projection_container_name,
            ),
            storage_client=storage,
            cosmos_client=cosmos,
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
            source_name='Blob Storage',
            projection_name='Cosmos DB',
        )
