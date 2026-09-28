from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
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
from ada.web.application.generic.resource_preparation import (
    ResourceObserver,
    ResourcePreparationReport,
    prepare_manager_resources,
)
from ada.web.application.generic.settings import AdaGenericSettings
from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.persistence import ToolProjectionProvider, ToolSourceProvider
from atlanticus.connectivity.cosmos import CosmosClient, CosmosSettings
from atlanticus.connectivity.storage import StorageClient, StorageSettings
from atlanticus.web.compositions.profiles_manager import PROFILES_CONFIGURATION_SOURCE_KEY
from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.users.blob.recovery import (
    BlobApprovedUsersSnapshotStore,
    BlobUsersRecoveryAuditStore,
    BlobUsersReplaceBeforeImageStore,
)
from atlanticus.web.users.recovery import UsersApprovedRecoveryService, UsersRecoveryConflictError

_STORAGE_CONNECTION = 'ada-blob'
_COSMOS_CONNECTION = 'ada-cosmos'


# La selección de persistencia pertenece al host y no modifica el modelo global de Tool.
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


# Reutilizamos exactamente las credenciales y la base Tool; los nombres físicos Cosmos
# proceden de los contratos vigentes, sin copiar secretos ni crear otro account.
def resolve_durable_manager_configuration(
    settings: AdaGenericSettings,
) -> DurableManagerConfiguration:
    if not isinstance(settings, AdaGenericSettings):
        raise TypeError('Manager deployment requires AdaGenericSettings')
    if settings.tool_source_provider is not ToolSourceProvider.BLOB:
        raise ValueError('Durable Manager requires the existing Tool Blob Source connection')
    if settings.tool_projection_provider is not ToolProjectionProvider.COSMOS:
        raise ValueError('Durable Manager requires the existing Tool Cosmos connection')
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


# El host conserva abiertos sus clientes durante todo el ciclo de vida web.
# No hay clientes globales ni IO de red durante la construcción de adaptadores.
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
        stores = _attach_users_recovery(stores, resolved, connections, settings)
        yield DurableManagerRuntime(
            stores=stores,
            resources=resolved.resources,
            connections=connections,
        )


# La preparación es una operación explícita posterior al despliegue Web.
# La validación no muta; ensure-local solo crea recursos Cosmos en desarrollo.
# Construye recuperación una sola vez sobre los stores durables existentes.
def _attach_users_recovery(
    stores: ConfigurationManagerStores,
    resolved: DurableManagerConfiguration,
    connections: ManagerPersistenceConnections,
    settings: AdaGenericSettings,
) -> ConfigurationManagerStores:
    resource = resolved.resources.users_registry
    client = connections.storage[resource.connection_ref]
    namespace = resolved.namespace

    def profiles_provider() -> ProfileCatalog:
        active = stores.profiles.get_active(PROFILES_CONFIGURATION_SOURCE_KEY)
        if active is None or not isinstance(active.payload, ProfileCatalog):
            raise UsersRecoveryConflictError('An active Profiles projection is required')
        return active.payload

    snapshots = BlobApprovedUsersSnapshotStore(
        client=client,
        container_name=resource.container_name,
        prefix=namespace.application_blob_name('users/recovery/snapshots'),
    )
    # No se consultan usuarios al construir Manager; el contexto se valida por operación.
    def recovery_provider() -> UsersApprovedRecoveryService:
        # La identidad real procede de promovidos, nunca del namespace de la herramienta.
        issuers = {user.issuer for user in stores.users_promoted.list_users()}
        if len(issuers) != 1:
            raise UsersRecoveryConflictError(
                'Users Projection requires one identifiable issuer among promoted users'
            )
        return UsersApprovedRecoveryService(
            registry=stores.users_registry,
            promoted=stores.users_promoted,
            replace_store=stores.users_promoted,
            profiles=profiles_provider,
            snapshots=snapshots,
            audit=BlobUsersRecoveryAuditStore(
                client=client,
                container_name=resource.container_name,
                prefix=namespace.application_blob_name('users/recovery/audit'),
            ),
            before_images=BlobUsersReplaceBeforeImageStore(
                client=client,
                container_name=resource.container_name,
                prefix=namespace.application_blob_name('users/recovery/replace-before'),
            ),
            application_key=namespace.application_namespace,
            identity_realm=next(iter(issuers)),
            environment=(
                f'{settings.environment.value}:{resolved.cosmos_settings.database_name}'
            ),
        )

    return replace(
        stores,
        users_recovery=recovery_provider,
        users_snapshot_ids=snapshots.list_snapshot_ids,
        users_snapshot_summaries=snapshots.list_snapshot_summaries,
        users_read_snapshot=snapshots.load,
    )


# La preparación mantiene resultados por recurso y no modifica Blob en producción.
def prepare_durable_manager_resources(
    deployment: DurableManagerRuntime,
    *,
    action: Literal['validate', 'prepare'],
    environment: WebEnvironment,
    observe_failure: ResourceObserver | None = None,
) -> ResourcePreparationReport:
    if not isinstance(deployment, DurableManagerRuntime):
        raise TypeError('Resource preparation requires a durable Manager runtime')
    return prepare_manager_resources(
        resources=deployment.resources,
        connections=deployment.connections,
        action=action,
        environment=environment,
        observe_failure=observe_failure,
    )



# El CLI registra errores de forma estructurada, imprime el informe y señala fallos al deploy.
def manager_resources_main(argv: Sequence[str] | None = None) -> None:
    from argparse import ArgumentParser
    import json

    from atlanticus.web.observability import configure_web_observability

    parser = ArgumentParser(description='Validate or prepare ADA Manager resources')
    parser.add_argument('action', choices=('validate', 'prepare'))
    options = parser.parse_args(argv)
    observer = configure_web_observability(application='ada-resource-preparation', json_output=True)

    def observe_failure(result):
        observer.error(
            'ada.resource.preparation.failed',
            'Resource preparation failed',
            resource_kind=result.kind,
            logical_id=result.logical_id,
            physical_name=result.physical_name,
            status=result.status.value,
            error_type=result.error_type,
        )

    try:
        settings = AdaGenericSettings()
        with open_durable_manager(settings) as deployment:
            report = prepare_durable_manager_resources(
                deployment,
                action=options.action,
                environment=settings.environment,
                observe_failure=observe_failure,
            )
    except Exception as error:
        observer.error(
            'ada.resource.preparation.unavailable',
            'Resource preparation could not be started',
            error_type=type(error).__name__,
        )
        raise SystemExit(2) from error
    print(json.dumps(report.to_dict(), ensure_ascii=False))
    if report.status != 'COMPLETED':
        raise SystemExit(1)
