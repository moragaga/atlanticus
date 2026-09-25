from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from ada.web.access.projection.cosmos import (
    ADA_ACCESS_PROJECTION_STORAGE_RESOURCE,
    CosmosAdaAccessProjectionStore,
    CosmosAdaAccessProjectionStoreSettings,
)
from ada.web.application.configuration_manager.wiring import ConfigurationManagerStores
from ada.web.kpis.definition.projection.cosmos import (
    KPI_DEFINITION_PROJECTION_STORAGE_RESOURCE,
    CosmosKpiDefinitionProjectionStore,
    CosmosKpiDefinitionProjectionStoreSettings,
)
from ada.web.kpis.registry.projection.cosmos import (
    KPI_REGISTRY_PROJECTION_STORAGE_RESOURCE,
    CosmosKpiRegistryProjectionStore,
    CosmosKpiRegistryProjectionStoreSettings,
)
from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.projection.cosmos import (
    TOOL_PROJECTION_STORAGE_RESOURCE,
    CosmosToolProjectionStore,
    CosmosToolProjectionStoreSettings,
)
from atlanticus.connectivity.cosmos import CosmosClient
from atlanticus.connectivity.storage import StorageClient
from atlanticus.web.navigation.projection.cosmos import (
    NAVIGATION_PROJECTION_STORAGE_RESOURCE,
    CosmosNavigationProjectionStore,
    CosmosNavigationProjectionStoreSettings,
)
from atlanticus.web.profiles.projection.cosmos import (
    PROFILES_PROJECTION_STORAGE_RESOURCE,
    CosmosProfilesProjectionStore,
    CosmosProfilesProjectionStoreSettings,
)
from atlanticus.web.source.blob import BlobSourceSettings, BlobSourceStore
from atlanticus.web.storage.topology import (
    ResolvedStoragePlan,
    ResolvedStorageResource,
    StorageResourceContract,
    StorageResourceOverride,
    resolve_storage_plan,
)
from atlanticus.web.users.blob import BlobUsersRegistryStore
from atlanticus.web.users.cosmos import CosmosUsersStore
from atlanticus.web.users.storage import (
    USERS_RUNTIME_STORAGE_RESOURCE,
    USERS_SUPPORT_STORAGE_RESOURCE,
)

ClientT = TypeVar('ClientT')

_COSMOS_CONTRACTS: dict[str, StorageResourceContract[Any]] = {
    'navigation': NAVIGATION_PROJECTION_STORAGE_RESOURCE,
    'users_support': USERS_SUPPORT_STORAGE_RESOURCE,
    'tools': TOOL_PROJECTION_STORAGE_RESOURCE,
    'kpi_registry': KPI_REGISTRY_PROJECTION_STORAGE_RESOURCE,
    'kpi_definitions': KPI_DEFINITION_PROJECTION_STORAGE_RESOURCE,
    'users_runtime': USERS_RUNTIME_STORAGE_RESOURCE,
}

_SUPPORT_CONSUMER_CONTRACTS = (
    PROFILES_PROJECTION_STORAGE_RESOURCE,
    ADA_ACCESS_PROJECTION_STORAGE_RESOURCE,
)


@dataclass(frozen=True, slots=True)
class ManagerBlobResource:
    connection_ref: str
    container_name: str

    def __post_init__(self) -> None:
        _require_name(self.connection_ref, 'Storage connection reference')
        _require_name(self.container_name, 'Storage container name')


@dataclass(frozen=True, slots=True)
class ManagerPersistenceResources:
    application_source: ManagerBlobResource
    tool_source: ManagerBlobResource
    users_registry: ManagerBlobResource
    cosmos_plan: ResolvedStoragePlan

    def __post_init__(self) -> None:
        for name in ('application_source', 'tool_source', 'users_registry'):
            if not isinstance(getattr(self, name), ManagerBlobResource):
                raise TypeError(f'Manager {name} must be a Blob resource')
        if not isinstance(self.cosmos_plan, ResolvedStoragePlan):
            raise TypeError('Manager Cosmos resources must use a resolved storage plan')
        _validate_cosmos_resources(self.cosmos_plan)


@dataclass(frozen=True, slots=True)
class ManagerPersistenceConnections:
    storage: Mapping[str, StorageClient]
    cosmos: Mapping[str, CosmosClient]

    def __post_init__(self) -> None:
        if not isinstance(self.storage, Mapping) or not isinstance(self.cosmos, Mapping):
            raise TypeError('Manager connections must be named mappings')
        for clients in (self.storage, self.cosmos):
            if any(not isinstance(name, str) or not name.strip() for name in clients):
                raise ValueError('Manager connection names must be nonempty strings')


def resolve_manager_cosmos_plan(
    overrides: Sequence[StorageResourceOverride],
) -> ResolvedStoragePlan:
    return resolve_storage_plan(tuple(_COSMOS_CONTRACTS.values()), overrides)


def resolve_manager_cosmos_plan_for_connection(connection_ref: str) -> ResolvedStoragePlan:
    _require_name(connection_ref, 'Cosmos connection reference')
    return resolve_manager_cosmos_plan(
        tuple(
            StorageResourceOverride(contract.logical_id, connection_ref=connection_ref)
            for contract in _COSMOS_CONTRACTS.values()
        )
    )


def compose_durable_manager_stores(
    *,
    namespace: AdaStorageNamespace,
    resources: ManagerPersistenceResources,
    connections: ManagerPersistenceConnections,
) -> ConfigurationManagerStores:
    if not isinstance(namespace, AdaStorageNamespace):
        raise TypeError('Manager namespace must be AdaStorageNamespace')
    if not isinstance(resources, ManagerPersistenceResources):
        raise TypeError('Manager resources must be ManagerPersistenceResources')
    if not isinstance(connections, ManagerPersistenceConnections):
        raise TypeError('Manager connections must be ManagerPersistenceConnections')

    physical = _validate_cosmos_resources(resources.cosmos_plan)
    storage = {
        name: _require_connection(connections.storage, getattr(resources, name).connection_ref)
        for name in ('application_source', 'tool_source', 'users_registry')
    }
    cosmos = {
        name: _require_connection(connections.cosmos, resolved.connection_ref)
        for name, resolved in physical.items()
    }

    application_source = BlobSourceStore(
        BlobSourceSettings(
            container_name=resources.application_source.container_name,
            root_prefix=namespace.application_prefix,
        ),
        storage=storage['application_source'],
    )
    tool_source = BlobSourceStore(
        BlobSourceSettings(
            container_name=resources.tool_source.container_name,
            root_prefix=namespace.tool_prefix,
        ),
        storage=storage['tool_source'],
    )
    users = CosmosUsersStore(
        client=cosmos['users_runtime'],
        container_name=physical['users_runtime'].physical_name,
    )
    return ConfigurationManagerStores(
        navigation_source=application_source,
        tools_source=tool_source,
        access_source=application_source,
        profiles_source=application_source,
        kpi_registry_source=tool_source,
        kpi_definitions_source=tool_source,
        navigation=CosmosNavigationProjectionStore(
            client=cosmos['navigation'],
            settings=CosmosNavigationProjectionStoreSettings(physical['navigation'].physical_name),
        ),
        profiles=CosmosProfilesProjectionStore(
            client=cosmos['users_support'],
            settings=CosmosProfilesProjectionStoreSettings(physical['users_support'].physical_name),
        ),
        access=CosmosAdaAccessProjectionStore(
            client=cosmos['users_support'],
            settings=CosmosAdaAccessProjectionStoreSettings(
                physical['users_support'].physical_name
            ),
        ),
        tools=CosmosToolProjectionStore(
            client=cosmos['tools'],
            settings=CosmosToolProjectionStoreSettings.from_namespace(
                container_name=physical['tools'].physical_name,
                namespace=namespace,
            ),
        ),
        kpi_registry=CosmosKpiRegistryProjectionStore(
            client=cosmos['kpi_registry'],
            settings=CosmosKpiRegistryProjectionStoreSettings(
                physical['kpi_registry'].physical_name
            ),
        ),
        kpi_definitions=CosmosKpiDefinitionProjectionStore(
            client=cosmos['kpi_definitions'],
            settings=CosmosKpiDefinitionProjectionStoreSettings(
                physical['kpi_definitions'].physical_name
            ),
        ),
        users_registry=BlobUsersRegistryStore(
            client=storage['users_registry'],
            container_name=resources.users_registry.container_name,
            blob_name=namespace.application_blob_name('users/users.json.gz'),
        ),
        users_promoted=users,
    )


def _validate_cosmos_resources(
    plan: ResolvedStoragePlan,
) -> dict[str, ResolvedStorageResource[Any]]:
    by_id = {resource.logical_id: resource for resource in plan.resources}
    if len(by_id) != len(plan.resources):
        raise ValueError('Manager Cosmos plan contains duplicated logical resources')
    if any(
        consumer.provider != USERS_SUPPORT_STORAGE_RESOURCE.provider
        or consumer.topology != USERS_SUPPORT_STORAGE_RESOURCE.topology
        for consumer in _SUPPORT_CONSUMER_CONTRACTS
    ):
        raise ValueError('Manager shared support resource has incompatible topology')
    physical = [
        (resource.provider, resource.connection_ref, resource.physical_name)
        for resource in plan.resources
    ]
    if len(set(physical)) != len(physical):
        raise ValueError('Manager Cosmos plan contains conflicting physical resources')
    if len({resource.connection_ref for resource in plan.resources}) != 1:
        raise ValueError('ADA Manager must use one Cosmos connection')
    expected = {contract.logical_id for contract in _COSMOS_CONTRACTS.values()}
    if set(by_id) != expected:
        raise ValueError('Manager Cosmos plan contains unexpected logical resources')
    result: dict[str, ResolvedStorageResource[Any]] = {}
    for name, contract in _COSMOS_CONTRACTS.items():
        resource = by_id.get(contract.logical_id)
        if resource is None:
            raise ValueError(f'Manager Cosmos plan is missing {contract.logical_id}')
        if (
            resource.owner != contract.owner
            or resource.provider != contract.provider
            or resource.physical_name != contract.default_physical_name
            or resource.topology != contract.topology
        ):
            raise ValueError(f'Manager Cosmos plan violates {contract.logical_id} topology')
        result[name] = resource
    return result


def _require_name(value: str, description: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{description} must be nonempty and normalized')


def _require_connection(clients: Mapping[str, ClientT], name: str) -> ClientT:
    if name not in clients or clients[name] is None:
        raise ValueError(f'Manager connection reference is not registered: {name}')
    return clients[name]
