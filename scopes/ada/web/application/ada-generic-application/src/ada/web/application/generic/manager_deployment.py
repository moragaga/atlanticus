from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ada.web.application.configuration_manager.wiring import ConfigurationManagerStores
from ada.web.application.generic.manager_persistence import (
    ManagerBlobResource,
    ManagerPersistenceConnections,
    ManagerPersistenceResources,
    compose_durable_manager_stores,
    resolve_manager_cosmos_plan_for_connection,
)
from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.persistence import ToolProjectionProvider, ToolSourceProvider
from ada.web.tools.projection.cosmos import TOOL_PROJECTION_STORAGE_RESOURCE
from atlanticus.connectivity.cosmos import CosmosClient, CosmosProvisioner, CosmosSettings
from atlanticus.connectivity.storage import StorageClient, StorageSettings
from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.storage.cosmos import (
    ensure_cosmos_storage_plan,
    validate_cosmos_storage_plan,
)

_STORAGE_CONNECTION = 'ada-blob'
_COSMOS_CONNECTION = 'ada-cosmos'


class ManagerStartupOptions(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file='.env',
        env_file_encoding='utf-8',
        env_prefix='',
        extra='ignore',
        frozen=True,
    )

    provider: Literal['auto', 'local', 'durable', 'disabled'] = Field(
        default='auto',
        validation_alias='ADA_MANAGER_PERSISTENCE_PROVIDER',
    )


@dataclass(frozen=True, slots=True)
class DurableManagerConfiguration:
    namespace: AdaStorageNamespace
    resources: ManagerPersistenceResources
    storage_settings: StorageSettings
    cosmos_settings: CosmosSettings


@dataclass(frozen=True, slots=True)
class DurableManagerRuntime:
    stores: ConfigurationManagerStores
    resources: ManagerPersistenceResources
    connections: ManagerPersistenceConnections


def resolve_durable_manager_configuration(
    settings: AdaGenericSettings,
) -> DurableManagerConfiguration:
    if not isinstance(settings, AdaGenericSettings):
        raise TypeError('Manager deployment requires AdaGenericSettings')
    if settings.tool_source_provider is not ToolSourceProvider.BLOB:
        raise ValueError('Durable Manager requires the existing Tool Blob Source connection')
    if settings.tool_projection_provider is not ToolProjectionProvider.COSMOS:
        raise ValueError('Durable Manager requires the existing Tool Cosmos connection')
    if (
        settings.tool_projection_cosmos_container_name
        != TOOL_PROJECTION_STORAGE_RESOURCE.default_physical_name
    ):
        raise ValueError('Tool Cosmos container conflicts with the canonical resource contract')

    storage_settings = settings.storage_settings()
    cosmos_settings = settings.tool_projection_cosmos_settings()
    container_name = settings.tool_source_blob_container_name
    if storage_settings is None or cosmos_settings is None or container_name is None:
        raise ValueError('Durable Manager provider settings are incomplete')
    delivery_settings = settings.kpi_delivery_cosmos_settings()
    if delivery_settings is not None and (
        delivery_settings.endpoint != cosmos_settings.endpoint
        or delivery_settings.database_name != cosmos_settings.database_name
    ):
        raise ValueError('ADA Manager and KPI delivery must share one Cosmos database')
    namespace = AdaStorageNamespace(
        application_namespace=settings.application_namespace,
        tool_namespace=settings.tool_namespace,
    )
    resource = ManagerBlobResource(
        connection_ref=_STORAGE_CONNECTION,
        container_name=container_name,
    )
    return DurableManagerConfiguration(
        namespace=namespace,
        resources=ManagerPersistenceResources(
            application_source=resource,
            tool_source=resource,
            users_registry=resource,
            cosmos_plan=resolve_manager_cosmos_plan_for_connection(_COSMOS_CONNECTION),
        ),
        storage_settings=storage_settings,
        cosmos_settings=cosmos_settings,
    )


@contextmanager
def open_durable_manager(
    settings: AdaGenericSettings,
) -> Iterator[DurableManagerRuntime]:
    resolved = resolve_durable_manager_configuration(settings)
    with ExitStack() as stack:
        storage = StorageClient(settings=resolved.storage_settings)
        stack.callback(storage.close)
        cosmos = CosmosClient(settings=resolved.cosmos_settings)
        stack.callback(cosmos.close)
        connections = ManagerPersistenceConnections(
            storage={_STORAGE_CONNECTION: storage},
            cosmos={_COSMOS_CONNECTION: cosmos},
        )
        stores = compose_durable_manager_stores(
            namespace=resolved.namespace,
            resources=resolved.resources,
            connections=connections,
        )
        yield DurableManagerRuntime(
            stores=stores,
            resources=resolved.resources,
            connections=connections,
        )


def prepare_durable_manager_resources(
    deployment: DurableManagerRuntime,
    *,
    action: Literal['validate', 'ensure-local'],
    environment: WebEnvironment,
) -> tuple[str, ...]:
    if not isinstance(deployment, DurableManagerRuntime):
        raise TypeError('Resource preparation requires a durable Manager runtime')
    if not isinstance(environment, WebEnvironment):
        raise TypeError('Resource preparation requires WebEnvironment')
    if action not in ('validate', 'ensure-local'):
        raise ValueError('Unknown Manager resource preparation action')
    if action == 'ensure-local' and not environment.is_local:
        raise ValueError('Manager resource creation is restricted to local environment')

    blobs = {
        (resource.connection_ref, resource.container_name)
        for resource in (
            deployment.resources.application_source,
            deployment.resources.tool_source,
            deployment.resources.users_registry,
        )
    }
    for connection_ref, container_name in sorted(blobs):
        deployment.connections.storage[connection_ref].health_check(container_name=container_name)

    cosmos_ref = deployment.resources.cosmos_plan.resources[0].connection_ref
    cosmos = deployment.connections.cosmos[cosmos_ref]
    provisioner = CosmosProvisioner(client=cosmos)
    provisioners = {cosmos_ref: provisioner}
    if action == 'ensure-local':
        provisioner.ensure_database()
        ensure_cosmos_storage_plan(
            deployment.resources.cosmos_plan,
            provisioners=provisioners,
        )
    else:
        validate_cosmos_storage_plan(
            deployment.resources.cosmos_plan,
            provisioners=provisioners,
        )
    return tuple(resource.physical_name for resource in deployment.resources.cosmos_plan.resources)


def manager_resources_main(argv: Sequence[str] | None = None) -> None:
    from argparse import ArgumentParser

    parser = ArgumentParser(description='Validate or prepare ADA Manager resources')
    parser.add_argument('action', choices=('validate', 'ensure-local'))
    options = parser.parse_args(argv)
    settings = AdaGenericSettings()
    with open_durable_manager(settings) as deployment:
        containers = prepare_durable_manager_resources(
            deployment,
            action=options.action,
            environment=settings.environment,
        )
    print(f'Manager resources {options.action}: {", ".join(containers)}')
