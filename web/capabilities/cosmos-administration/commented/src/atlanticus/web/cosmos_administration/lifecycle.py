from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from atlanticus.connectivity.cosmos import CosmosClient, CosmosContainerSpec, CosmosProvisioner
from atlanticus.web.storage.cosmos import to_cosmos_container_spec
from atlanticus.web.storage.topology import ResolvedStoragePlan


# Fallo de configuración: no se permite seleccionar recursos no aprobados.
class CosmosLifecycleConfigurationError(ValueError):
    pass


# Contenedor físico derivado de un recurso lógico del plan consolidado.
@dataclass(frozen=True, slots=True)
class CosmosManagedContainer:
    logical_id: str
    connection_ref: str
    database_name: str
    spec: CosmosContainerSpec


# Resultado observable sin exponer detalles internos del SDK de Azure.
@dataclass(frozen=True, slots=True)
class CosmosLifecycleReport:
    action: Literal['validate', 'prepare']
    status: Literal['READY', 'CREATED']
    container: CosmosManagedContainer
    database_created: bool = False


# Orquesta operaciones Cosmos ya existentes y nunca ejecuta eliminación.
class CosmosLifecycleService:
    def __init__(
        self,
        *,
        connections: Mapping[str, CosmosClient],
        plan: ResolvedStoragePlan,
    ) -> None:
        if not isinstance(connections, Mapping) or not connections:
            raise CosmosLifecycleConfigurationError('Named Cosmos connections are required')
        normalized: dict[str, CosmosClient] = {}
        for connection_ref, client in connections.items():
            if (
                not isinstance(connection_ref, str)
                or not connection_ref
                or connection_ref != connection_ref.strip()
                or not isinstance(client, CosmosClient)
            ):
                raise CosmosLifecycleConfigurationError('Cosmos connection binding is invalid')
            normalized[connection_ref] = client
        if not isinstance(plan, ResolvedStoragePlan):
            raise CosmosLifecycleConfigurationError(
                'Approved Cosmos resources require a resolved plan'
            )
        managed: dict[str, CosmosManagedContainer] = {}
        physical: set[tuple[str, str]] = set()
        # Sólo son administrables los recursos Cosmos presentes en la topología resuelta.
        for resource in plan.resources:
            if resource.provider != 'cosmos':
                continue
            client = normalized.get(resource.connection_ref)
            if client is None:
                raise CosmosLifecycleConfigurationError(
                    'Approved Cosmos connection is not configured'
                )
            spec = to_cosmos_container_spec(resource)
            binding = (resource.connection_ref, spec.name)
            if resource.logical_id in managed or binding in physical:
                raise CosmosLifecycleConfigurationError(
                    'Approved Cosmos container binding is duplicated'
                )
            managed[resource.logical_id] = CosmosManagedContainer(
                logical_id=resource.logical_id,
                connection_ref=resource.connection_ref,
                database_name=client.settings.database_name,
                spec=spec,
            )
            physical.add(binding)
        self._connections = normalized
        self._managed = managed

    def list_managed_containers(self) -> tuple[CosmosManagedContainer, ...]:
        return tuple(self._managed[key] for key in sorted(self._managed))

    def validate_container(self, *, logical_id: str) -> CosmosLifecycleReport:
        container, client = self._resolve(logical_id)
        CosmosProvisioner(client=client).validate_containers((container.spec,))
        return CosmosLifecycleReport(action='validate', status='READY', container=container)

    def prepare_container(self, *, logical_id: str) -> CosmosLifecycleReport:
        container, client = self._resolve(logical_id)
        provisioner = CosmosProvisioner(client=client)
        database_created = provisioner.ensure_database()
        # Ensure es idempotente; una definición física incompatible causa error.
        created = provisioner.ensure_containers((container.spec,))
        # El aprovisionador valida existentes; se verifica después de una creación nueva.
        if created:
            provisioner.validate_containers((container.spec,))
        return CosmosLifecycleReport(
            action='prepare',
            status='CREATED' if created else 'READY',
            container=container,
            database_created=database_created,
        )

    def _resolve(self, logical_id: str) -> tuple[CosmosManagedContainer, CosmosClient]:
        if not isinstance(logical_id, str) or logical_id not in self._managed:
            raise CosmosLifecycleConfigurationError('Cosmos resource is not approved')
        container = self._managed[logical_id]
        return container, self._connections[container.connection_ref]
