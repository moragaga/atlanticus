from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Literal

from ada.web.application.generic.manager_persistence import (
    ManagerPersistenceConnections,
    ManagerPersistenceResources,
)
from atlanticus.connectivity.cosmos import (
    CosmosContainerDefinitionMismatchError,
    CosmosContainerNotFoundError,
    CosmosDatabaseNotFoundError,
    CosmosProvisioner,
)
from atlanticus.connectivity.storage import (
    StorageConnectionStringCredential,
    StorageContainerNotFoundError,
    StorageSasCredential,
    StorageSettings,
)
from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.storage.cosmos import to_cosmos_container_spec

_LOGGER = logging.getLogger(__name__)

ResourceKind = Literal['blob-container', 'cosmos-database', 'cosmos-container']
ResourceAction = Literal['validate', 'prepare']
ResourceObserver = Callable[['ResourcePreparationResult'], None]


# Los estados son resultados operativos; no sustituyen los estados de ProjectionTarget.
class ResourcePreparationStatus(StrEnum):
    READY = 'READY'
    CREATED = 'CREATED'
    MISSING = 'MISSING'
    INCOMPATIBLE = 'INCOMPATIBLE'
    FAILED = 'FAILED'
    BLOCKED = 'BLOCKED'
    SKIPPED = 'SKIPPED'


@dataclass(frozen=True, slots=True)
# Resultado inmutable y seguro: no guarda errores crudos ni secretos de conexión.
class ResourcePreparationResult:
    kind: ResourceKind
    logical_id: str
    physical_name: str
    status: ResourcePreparationStatus
    error_type: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
# Un informe agrupa éxitos y fallos sin transacciones distribuidas.
class ResourcePreparationReport:
    action: ResourceAction
    environment: WebEnvironment
    results: tuple[ResourcePreparationResult, ...]

    @property
    def status(self) -> str:
        failed = any(
            item.status in (
                ResourcePreparationStatus.MISSING,
                ResourcePreparationStatus.INCOMPATIBLE,
                ResourcePreparationStatus.FAILED,
                ResourcePreparationStatus.BLOCKED,
            )
            for item in self.results
        )
        if not failed:
            return 'COMPLETED'
        progressed = any(
            item.status in (ResourcePreparationStatus.CREATED, ResourcePreparationStatus.READY)
            for item in self.results
        )
        return 'PARTIAL' if progressed else 'FAILED'

    def to_dict(self) -> dict[str, object]:
        return {
            'action': self.action,
            'environment': self.environment.value,
            'status': self.status,
            'results': [item.to_dict() for item in self.results],
        }


# Crear Blob es una excepción exclusiva del ambiente local; producción nunca llama aquí.
def ensure_local_blob_container(settings: StorageSettings, container_name: str) -> bool:
    from azure.core.exceptions import ResourceExistsError
    from azure.storage.blob import BlobServiceClient

    credential = settings.credential
    if isinstance(credential, StorageConnectionStringCredential):
        client = BlobServiceClient.from_connection_string(credential.connection_string)
    elif isinstance(credential, StorageSasCredential):
        client = BlobServiceClient(
            account_url=credential.account_url,
            credential=credential.sas_token,
        )
    else:
        raise TypeError('Unsupported Storage credential for local resource preparation')
    with client:
        target = client.get_container_client(container_name)
        if target.exists():
            return False
        try:
            client.create_container(container_name)
        except ResourceExistsError:
            if not target.exists():
                raise
            return False
    return True


# La misma operación sirve al job de despliegue y al diagnóstico posterior de Master.
# La base productiva se comprueba sin intentar crearla.
def prepare_manager_resources(
    *,
    resources: ManagerPersistenceResources,
    connections: ManagerPersistenceConnections,
    action: ResourceAction,
    environment: WebEnvironment,
    observe_failure: ResourceObserver | None = None,
) -> ResourcePreparationReport:
    if not isinstance(resources, ManagerPersistenceResources):
        raise TypeError('Resource preparation requires ManagerPersistenceResources')
    if not isinstance(connections, ManagerPersistenceConnections):
        raise TypeError('Resource preparation requires ManagerPersistenceConnections')
    if not isinstance(environment, WebEnvironment):
        raise TypeError('Resource preparation requires WebEnvironment')
    if action not in ('validate', 'prepare'):
        raise ValueError('Unknown resource preparation action')
    if observe_failure is not None and not callable(observe_failure):
        raise TypeError('observe_failure must be callable')

    results: list[ResourcePreparationResult] = []

    def failure_status(error: Exception) -> ResourcePreparationStatus:
        if isinstance(error, CosmosContainerDefinitionMismatchError):
            return ResourcePreparationStatus.INCOMPATIBLE
        if isinstance(
            error,
            (CosmosContainerNotFoundError, CosmosDatabaseNotFoundError,
             StorageContainerNotFoundError),
        ):
            return ResourcePreparationStatus.MISSING
        return ResourcePreparationStatus.FAILED

    def add(
        kind: ResourceKind,
        logical_id: str,
        physical_name: str,
        status: ResourcePreparationStatus,
        error: Exception | None = None,
    ) -> None:
        result = ResourcePreparationResult(
            kind=kind,
            logical_id=logical_id,
            physical_name=physical_name,
            status=status,
            error_type=(type(error).__name__ if error is not None else None),
        )
        results.append(result)
        if error is not None:
            if observe_failure is None:
                _LOGGER.error(
                    'event=resource.preparation.failed kind=%s logical_id=%s status=%s error_type=%s',
                    kind, logical_id, status.value, type(error).__name__,
                )
            else:
                try:
                    observe_failure(result)
                except Exception as observer_error:
                    _LOGGER.error(
                        'event=resource.preparation.observer.failed error_type=%s',
                        type(observer_error).__name__,
                    )

    # Deduplicamos recursos físicos Blob compartidos por varios Sources.
    blobs = {
        (resource.connection_ref, resource.container_name)
        for resource in (
            resources.application_source,
            resources.tool_source,
            resources.users_registry,
        )
    }
    for connection_ref, name in sorted(blobs):
        if environment.is_production:
            add('blob-container', connection_ref, name, ResourcePreparationStatus.SKIPPED)
            continue
        try:
            storage = connections.storage[connection_ref]
            if action == 'prepare':
                created = ensure_local_blob_container(storage.settings, name)
                status = ResourcePreparationStatus.CREATED if created else ResourcePreparationStatus.READY
            else:
                storage.health_check(container_name=name)
                status = ResourcePreparationStatus.READY
            add('blob-container', connection_ref, name, status)
        except Exception as error:
            add('blob-container', connection_ref, name, failure_status(error), error)

    plan = resources.cosmos_plan
    ordered = tuple(sorted(plan.resources, key=lambda value: (value.connection_ref, value.logical_id)))
    refs = sorted({resource.connection_ref for resource in ordered})
    provisioners: dict[str, CosmosProvisioner] = {}
    ready_refs: set[str] = set()
    # Una base indisponible bloquea sólo sus contenedores dependientes.
    for connection_ref in refs:
        database_name = '<unavailable>'
        try:
            cosmos = connections.cosmos[connection_ref]
            database_name = cosmos.settings.database_name
            provisioner = CosmosProvisioner(client=cosmos)
            provisioners[connection_ref] = provisioner
            if action == 'prepare' and environment.is_local:
                created = provisioner.ensure_database()
                status = ResourcePreparationStatus.CREATED if created else ResourcePreparationStatus.READY
            else:
                cosmos.health_check()
                status = ResourcePreparationStatus.READY
            ready_refs.add(connection_ref)
            add('cosmos-database', connection_ref, database_name, status)
        except Exception as error:
            add(
                'cosmos-database', connection_ref, database_name,
                failure_status(error), error,
            )

    # Cada contenedor se prepara aisladamente para no ocultar éxitos parciales.
    for resource in ordered:
        if resource.connection_ref not in ready_refs:
            add(
                'cosmos-container', resource.logical_id, resource.physical_name,
                ResourcePreparationStatus.BLOCKED,
            )
            continue
        try:
            spec = to_cosmos_container_spec(resource)
            provisioner = provisioners[resource.connection_ref]
            if action == 'prepare':
                created = provisioner.ensure_containers((spec,))
                status = (
                    ResourcePreparationStatus.CREATED if created else ResourcePreparationStatus.READY
                )
            else:
                provisioner.validate_containers((spec,))
                status = ResourcePreparationStatus.READY
            add('cosmos-container', resource.logical_id, resource.physical_name, status)
        except Exception as error:
            add(
                'cosmos-container', resource.logical_id, resource.physical_name,
                failure_status(error), error,
            )

    return ResourcePreparationReport(action=action, environment=environment, results=tuple(results))
