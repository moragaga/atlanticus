from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Literal

from atlanticus.connectivity.cosmos import (
    CosmosClient,
    CosmosContainerDefinitionMismatchError,
    CosmosContainerNotFoundError,
    CosmosDatabaseNotFoundError,
    CosmosProvisioner,
)
from atlanticus.connectivity.storage import (
    StorageClient,
    StorageConnectionStringCredential,
    StorageContainerNotFoundError,
    StorageSasCredential,
    StorageSettings,
)
from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.storage.cosmos import to_cosmos_container_spec
from atlanticus.web.storage.topology import ResolvedStoragePlan

_LOGGER = logging.getLogger(__name__)

ResourceKind = Literal['blob-container', 'cosmos-database', 'cosmos-container']
ResourceAction = Literal['validate', 'prepare']
ResourceObserver = Callable[['ResourcePreparationResult'], None]


class ResourcePreparationStatus(StrEnum):
    READY = 'READY'
    CREATED = 'CREATED'
    MISSING = 'MISSING'
    INCOMPATIBLE = 'INCOMPATIBLE'
    FAILED = 'FAILED'
    BLOCKED = 'BLOCKED'
    SKIPPED = 'SKIPPED'


@dataclass(frozen=True, slots=True)
class BlobContainerResource:
    logical_id: str
    connection_ref: str
    container_name: str

    def __post_init__(self) -> None:
        _require_text(self.logical_id, 'Blob logical id')
        _require_text(self.connection_ref, 'Blob connection reference')
        _require_text(self.container_name, 'Blob container name')


@dataclass(frozen=True, slots=True)
class ResourcePreparationResources:
    blob_containers: tuple[BlobContainerResource, ...]
    cosmos_plan: ResolvedStoragePlan

    def __post_init__(self) -> None:
        try:
            blobs = tuple(self.blob_containers)
        except TypeError:
            raise TypeError('Blob resources must be an iterable') from None
        if any(not isinstance(resource, BlobContainerResource) for resource in blobs):
            raise TypeError('Blob resources must contain BlobContainerResource values')
        physical = [(resource.connection_ref, resource.container_name) for resource in blobs]
        if len(physical) != len(set(physical)):
            raise ValueError('Blob resources must not repeat a physical container binding')
        if not isinstance(self.cosmos_plan, ResolvedStoragePlan):
            raise TypeError('Cosmos resources must use a resolved storage plan')
        object.__setattr__(self, 'blob_containers', blobs)


@dataclass(frozen=True, slots=True)
class ResourcePreparationConnections:
    storage: Mapping[str, StorageClient]
    cosmos: Mapping[str, CosmosClient]

    def __post_init__(self) -> None:
        if not isinstance(self.storage, Mapping) or not isinstance(self.cosmos, Mapping):
            raise TypeError('Resource connections must be named mappings')
        for clients in (self.storage, self.cosmos):
            if any(
                not isinstance(name, str) or not name or name != name.strip() for name in clients
            ):
                raise ValueError('Resource connection names must be nonempty normalized strings')


@dataclass(frozen=True, slots=True)
class ResourcePreparationResult:
    kind: ResourceKind
    logical_id: str
    physical_name: str
    status: ResourcePreparationStatus
    error_type: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResourcePreparationReport:
    action: ResourceAction
    environment: WebEnvironment
    results: tuple[ResourcePreparationResult, ...]

    @property
    def status(self) -> str:
        failed = any(
            item.status
            in (
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


def prepare_resources(
    *,
    resources: ResourcePreparationResources,
    connections: ResourcePreparationConnections,
    action: ResourceAction,
    environment: WebEnvironment,
    observe_failure: ResourceObserver | None = None,
) -> ResourcePreparationReport:
    if not isinstance(resources, ResourcePreparationResources):
        raise TypeError('Resource preparation requires ResourcePreparationResources')
    if not isinstance(connections, ResourcePreparationConnections):
        raise TypeError('Resource preparation requires ResourcePreparationConnections')
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
            (
                CosmosContainerNotFoundError,
                CosmosDatabaseNotFoundError,
                StorageContainerNotFoundError,
            ),
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
                    'event=resource.preparation.failed kind=%s logical_id=%s '
                    'status=%s error_type=%s',
                    kind,
                    logical_id,
                    status.value,
                    type(error).__name__,
                )
            else:
                try:
                    observe_failure(result)
                except Exception as observer_error:
                    _LOGGER.error(
                        'event=resource.preparation.observer.failed error_type=%s',
                        type(observer_error).__name__,
                    )

    for resource in sorted(
        resources.blob_containers,
        key=lambda value: (value.connection_ref, value.container_name, value.logical_id),
    ):
        if environment.is_production:
            add(
                'blob-container',
                resource.logical_id,
                resource.container_name,
                ResourcePreparationStatus.SKIPPED,
            )
            continue
        try:
            storage = connections.storage[resource.connection_ref]
            if action == 'prepare':
                created = ensure_local_blob_container(storage.settings, resource.container_name)
                status = (
                    ResourcePreparationStatus.CREATED
                    if created
                    else ResourcePreparationStatus.READY
                )
            else:
                storage.health_check(container_name=resource.container_name)
                status = ResourcePreparationStatus.READY
            add('blob-container', resource.logical_id, resource.container_name, status)
        except Exception as error:
            add(
                'blob-container',
                resource.logical_id,
                resource.container_name,
                failure_status(error),
                error,
            )

    ordered = tuple(
        sorted(
            resources.cosmos_plan.resources,
            key=lambda value: (value.connection_ref, value.logical_id),
        )
    )
    refs = sorted({resource.connection_ref for resource in ordered})
    provisioners: dict[str, CosmosProvisioner] = {}
    ready_refs: set[str] = set()
    for connection_ref in refs:
        database_name = '<unavailable>'
        try:
            cosmos = connections.cosmos[connection_ref]
            database_name = cosmos.settings.database_name
            provisioner = CosmosProvisioner(client=cosmos)
            provisioners[connection_ref] = provisioner
            if action == 'prepare' and environment.is_local:
                created = provisioner.ensure_database()
                status = (
                    ResourcePreparationStatus.CREATED
                    if created
                    else ResourcePreparationStatus.READY
                )
            else:
                cosmos.health_check()
                status = ResourcePreparationStatus.READY
            ready_refs.add(connection_ref)
            add('cosmos-database', connection_ref, database_name, status)
        except Exception as error:
            add(
                'cosmos-database',
                connection_ref,
                database_name,
                failure_status(error),
                error,
            )

    for resource in ordered:
        if resource.connection_ref not in ready_refs:
            add(
                'cosmos-container',
                resource.logical_id,
                resource.physical_name,
                ResourcePreparationStatus.BLOCKED,
            )
            continue
        try:
            spec = to_cosmos_container_spec(resource)
            provisioner = provisioners[resource.connection_ref]
            if action == 'prepare':
                created = provisioner.ensure_containers((spec,))
                status = (
                    ResourcePreparationStatus.CREATED
                    if created
                    else ResourcePreparationStatus.READY
                )
            else:
                provisioner.validate_containers((spec,))
                status = ResourcePreparationStatus.READY
            add('cosmos-container', resource.logical_id, resource.physical_name, status)
        except Exception as error:
            add(
                'cosmos-container',
                resource.logical_id,
                resource.physical_name,
                failure_status(error),
                error,
            )

    return ResourcePreparationReport(action=action, environment=environment, results=tuple(results))


def _require_text(value: object, description: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f'{description} must be nonempty normalized text')
