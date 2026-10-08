# Espejo pedagógico: conserva exactamente el comportamiento del archivo productivo.
# Los comentarios documentan intención, ownership y flujo sin agregar compatibilidad ni lógica alternativa.
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass

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
from ada_command_center.web.application.configuration_manager.administration import (
    CommandCenterAdministrationStores,
    compose_command_center_administration,
)
from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    resolve_command_center_namespace,
    STORAGE_CONTAINER_VARIABLE,
    ManagerConfigurationReader,
    catalog_storage_settings,
)
from ada_command_center.web.application.configuration_manager.dependencies import (
    ConfigurationManagerDependencies,
)
from ada_command_center.web.tools.catalog import BlobToolCatalogStore, BlobToolCatalogStoreSettings
from ada_command_center.web.tools.discovery_cosmos.manager import ToolCatalogManagerService
from atlanticus.connectivity.cosmos import CosmosClient, CosmosSettings
from atlanticus.connectivity.storage import StorageClient, StorageSettings
from atlanticus.web.compositions.profiles_manager import PROFILES_CONFIGURATION_SOURCE_KEY
from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.navigation.projection.cosmos import (
    NAVIGATION_PROJECTION_STORAGE_RESOURCE,
    CosmosNavigationProjectionStore,
    CosmosNavigationProjectionStoreSettings,
)
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.profiles.projection.cosmos import (
    PROFILES_PROJECTION_STORAGE_RESOURCE,
    CosmosProfilesProjectionStore,
    CosmosProfilesProjectionStoreSettings,
)
from atlanticus.web.storage.namespace import StorageNamespace
from atlanticus.web.storage.topology import (
    ResolvedStoragePlan,
    StorageResourceOverride,
    resolve_storage_plan,
)
from atlanticus.web.users.blob import (
    BlobToolMembershipStore,
    BlobToolUsersRecoverySnapshotStore,
    BlobUsersRecoveryAuditStore,
    BlobUsersRegistryStore,
    BlobUsersReplaceBeforeImageStore,
)
from atlanticus.web.users.cosmos import CosmosUsersRuntimeStore
from atlanticus.web.users.models import build_runtime_user
from atlanticus.web.users.profiles import require_managed_profile
from atlanticus.web.users.recovery import ToolUsersRecoveryService, UsersRecoveryConflictError
from atlanticus.web.users.storage import USERS_RUNTIME_STORAGE_RESOURCE

_COSMOS_CONNECTION_REF = 'command-center-cosmos'
_COSMOS_RESOURCES = (
    ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE,
    PROFILES_PROJECTION_STORAGE_RESOURCE,
    NAVIGATION_PROJECTION_STORAGE_RESOURCE,
    USERS_RUNTIME_STORAGE_RESOURCE,
)


@dataclass(frozen=True, slots=True)
class CommandCenterDurableConfiguration:
    namespace: StorageNamespace
    storage_settings: StorageSettings
    cosmos_settings: CosmosSettings
    cosmos_plan: ResolvedStoragePlan
    storage_container_name: str
    catalog_blob_name: str
    source_root_prefix: str
    users_registry_blob_name: str
    users_membership_blob_name: str
    alarm_projection_container_name: str
    profiles_projection_container_name: str
    navigation_projection_container_name: str
    users_runtime_container_name: str


@dataclass(frozen=True, slots=True)
class CommandCenterDurableRuntime:
    configuration: CommandCenterDurableConfiguration
    storage: StorageClient
    cosmos: CosmosClient


def _require(values: Mapping[str, str], name: str) -> str:
    value = values.get(name)
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ValueError(f'Command Center configuration is missing or invalid: {name}')
    return value


def resolve_durable_configuration(
    values: Mapping[str, str], *, local: bool
) -> CommandCenterDurableConfiguration:
    namespace = resolve_command_center_namespace(values)
    plan = resolve_storage_plan(
        _COSMOS_RESOURCES,
        tuple(
            StorageResourceOverride(
                logical_id=contract.logical_id,
                connection_ref=_COSMOS_CONNECTION_REF,
            )
            for contract in _COSMOS_RESOURCES
        ),
    )
    resources = {resource.logical_id: resource for resource in plan.resources}
    if len(resources) != len(_COSMOS_RESOURCES):
        raise ValueError('Command Center Cosmos topology is incomplete')
    for contract in _COSMOS_RESOURCES:
        resource = resources.get(contract.logical_id)
        if resource is None or (
            resource.owner != contract.owner
            or resource.provider != contract.provider
            or resource.physical_name != contract.default_physical_name
            or resource.topology != contract.topology
        ):
            raise ValueError(f'Command Center Cosmos topology is invalid: {contract.logical_id}')
    return CommandCenterDurableConfiguration(
        namespace=namespace,
        storage_settings=catalog_storage_settings(values, allow_insecure_http=local),
        cosmos_settings=CosmosSettings(
            endpoint=_require(values, 'ADA_COMMAND_CENTER_COSMOS_ENDPOINT'),
            database_name=_require(values, 'ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME'),
            key=_require(values, 'ADA_COMMAND_CENTER_COSMOS_KEY'),
            allow_insecure_http=local,
        ),
        cosmos_plan=plan,
        storage_container_name=_require(values, STORAGE_CONTAINER_VARIABLE),
        catalog_blob_name=namespace.scope_blob_name('tool-catalog/current.json'),
        source_root_prefix=namespace.scope_prefix,
        users_registry_blob_name=namespace.application_blob_name('users/users.json.gz'),
        users_membership_blob_name=namespace.scope_blob_name('users/memberships.json.gz'),
        alarm_projection_container_name=resources[
            ALARM_CONFIGURATION_PROJECTION_STORAGE_RESOURCE.logical_id
        ].physical_name,
        profiles_projection_container_name=resources[
            PROFILES_PROJECTION_STORAGE_RESOURCE.logical_id
        ].physical_name,
        navigation_projection_container_name=resources[
            NAVIGATION_PROJECTION_STORAGE_RESOURCE.logical_id
        ].physical_name,
        users_runtime_container_name=resources[
            USERS_RUNTIME_STORAGE_RESOURCE.logical_id
        ].physical_name,
    )


@contextmanager
def open_command_center_durable_runtime(
    *,
    reader: ManagerConfigurationReader,
) -> Iterator[CommandCenterDurableRuntime]:
    if not isinstance(reader, ManagerConfigurationReader):
        raise TypeError('Command Center durable runtime requires ManagerConfigurationReader')
    if reader.manager_provider != 'durable':
        raise ValueError('Durable Manager requires durable provider')
    resolved = resolve_durable_configuration(
        reader.own(), local=reader.environment is WebEnvironment.LOCAL
    )
    with ExitStack() as stack:
        storage = StorageClient(settings=resolved.storage_settings)
        stack.callback(storage.close)
        cosmos = CosmosClient(settings=resolved.cosmos_settings)
        stack.callback(cosmos.close)
        yield CommandCenterDurableRuntime(
            configuration=resolved,
            storage=storage,
            cosmos=cosmos,
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
    with open_command_center_durable_runtime(reader=reader) as runtime:
        resolved = runtime.configuration
        storage = runtime.storage
        cosmos = runtime.cosmos
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
                blob_root_prefix=resolved.source_root_prefix,
                cosmos_container_name=resolved.alarm_projection_container_name,
            ),
            storage_client=storage,
            cosmos_client=cosmos,
        )
        profiles = CosmosProfilesProjectionStore(
            client=cosmos,
            settings=CosmosProfilesProjectionStoreSettings(
                resolved.profiles_projection_container_name
            ),
        )
        navigation = CosmosNavigationProjectionStore(
            client=cosmos,
            settings=CosmosNavigationProjectionStoreSettings(
                resolved.navigation_projection_container_name
            ),
        )
        users_registry = BlobUsersRegistryStore(
            client=storage,
            container_name=resolved.storage_container_name,
            blob_name=resolved.users_registry_blob_name,
        )
        users_memberships = BlobToolMembershipStore(
            client=storage,
            container_name=resolved.storage_container_name,
            blob_name=resolved.users_membership_blob_name,
        )
        users_runtime = CosmosUsersRuntimeStore(
            client=cosmos,
            container_name=resolved.users_runtime_container_name,
        )

        def profiles_provider() -> ProfileCatalog:
            active = profiles.get_active(PROFILES_CONFIGURATION_SOURCE_KEY)
            if active is None or not isinstance(active.payload, ProfileCatalog):
                raise UsersRecoveryConflictError('An active Profiles projection is required')
            return active.payload

        def materialize_runtime_users():
            registry = users_registry.load()
            memberships = users_memberships.load()
            profile_catalog = profiles_provider()
            users = []
            for membership in memberships.memberships:
                identity = registry.get(membership.user_id)
                if identity is None:
                    raise UsersRecoveryConflictError(
                        'Tool membership user is missing from global Users registry'
                    )
                profile = require_managed_profile(
                    membership.profile_key,
                    profiles=profile_catalog,
                )
                users.append(
                    build_runtime_user(
                        identity=identity,
                        membership=membership,
                        profile=profile,
                    )
                )
            return tuple(sorted(users, key=lambda user: user.user_id))

        snapshots = BlobToolUsersRecoverySnapshotStore(
            client=storage,
            container_name=resolved.storage_container_name,
            prefix=resolved.namespace.scope_blob_name('users/recovery/snapshots'),
        )

        def recovery_provider() -> ToolUsersRecoveryService:
            return ToolUsersRecoveryService(
                runtime=users_runtime,
                materialize=materialize_runtime_users,
                snapshots=snapshots,
                audit=BlobUsersRecoveryAuditStore(
                    client=storage,
                    container_name=resolved.storage_container_name,
                    prefix=resolved.namespace.scope_blob_name('users/recovery/audit'),
                ),
                before_images=BlobUsersReplaceBeforeImageStore(
                    client=storage,
                    container_name=resolved.storage_container_name,
                    prefix=resolved.namespace.scope_blob_name('users/recovery/replace-before'),
                ),
                environment=f'{reader.environment.value}:{resolved.cosmos_settings.database_name}',
            )

        administration = compose_command_center_administration(
            stores=CommandCenterAdministrationStores(
                profiles_source=persistence.source,
                navigation_source=persistence.source,
                profiles=profiles,
                navigation=navigation,
                users_registry=users_registry,
                users_memberships=users_memberships,
                users_runtime=users_runtime,
                users_recovery=recovery_provider,
                users_snapshot_ids=snapshots.list_snapshot_ids,
                users_snapshot_summaries=snapshots.list_snapshot_summaries,
                users_read_snapshot=snapshots.load,
            ),
            principal_provider=principal_provider,
            source_name='Blob Storage',
            projection_name='Cosmos DB',
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
            administration=administration,
        )
