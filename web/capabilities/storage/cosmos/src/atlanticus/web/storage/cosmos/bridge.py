from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from atlanticus.connectivity.cosmos import CosmosContainerSpec, CosmosProvisioner
from atlanticus.web.storage.cosmos.errors import (
    CosmosContainerBindingConflictError,
    CosmosStorageBridgeConfigurationError,
    CosmosStorageTopologyMismatchError,
    InvalidCosmosProvisionerError,
    MissingCosmosProvisionerError,
)
from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    ResolvedStoragePlan,
    ResolvedStorageResource,
)

_COSMOS_PROVIDER = 'cosmos'


def to_cosmos_container_spec(
    resource: ResolvedStorageResource[Any],
) -> CosmosContainerSpec:
    if not isinstance(resource, ResolvedStorageResource):
        raise CosmosStorageBridgeConfigurationError('resource must be ResolvedStorageResource')
    if resource.provider != _COSMOS_PROVIDER:
        raise CosmosStorageBridgeConfigurationError(
            f'resource provider must be {_COSMOS_PROVIDER!r}'
        )
    topology = resource.topology
    if not isinstance(topology, CosmosContainerTopology):
        raise CosmosStorageTopologyMismatchError(
            logical_id=resource.logical_id,
            topology_type=type(topology).__name__,
        )
    return CosmosContainerSpec(
        name=resource.physical_name,
        partition_key_path=topology.partition_key_path,
        default_ttl_seconds=topology.default_ttl_seconds,
    )


def ensure_cosmos_storage_plan(
    plan: ResolvedStoragePlan,
    *,
    provisioners: Mapping[str, CosmosProvisioner],
) -> None:
    prepared = _prepare_cosmos_groups(plan=plan, provisioners=provisioners)
    for provisioner, specs in prepared:
        provisioner.ensure_containers(specs)


def validate_cosmos_storage_plan(
    plan: ResolvedStoragePlan,
    *,
    provisioners: Mapping[str, CosmosProvisioner],
) -> None:
    prepared = _prepare_cosmos_groups(plan=plan, provisioners=provisioners)
    for provisioner, specs in prepared:
        provisioner.validate_containers(specs)


def _prepare_cosmos_groups(
    *,
    plan: ResolvedStoragePlan,
    provisioners: Mapping[str, CosmosProvisioner],
) -> tuple[tuple[CosmosProvisioner, tuple[CosmosContainerSpec, ...]], ...]:
    if not isinstance(plan, ResolvedStoragePlan):
        raise CosmosStorageBridgeConfigurationError('plan must be ResolvedStoragePlan')
    if not isinstance(provisioners, Mapping):
        raise CosmosStorageBridgeConfigurationError('provisioners must be a mapping')

    resources = sorted(
        (resource for resource in plan.resources if resource.provider == _COSMOS_PROVIDER),
        key=lambda resource: (
            resource.connection_ref,
            resource.logical_id,
            resource.physical_name,
        ),
    )
    grouped: dict[str, list[tuple[str, CosmosContainerSpec]]] = {}
    owners: dict[tuple[str, str], str] = {}

    for resource in resources:
        spec = to_cosmos_container_spec(resource)
        physical_key = (resource.connection_ref, spec.name)
        conflicting_logical_id = owners.get(physical_key)
        if conflicting_logical_id is not None:
            raise CosmosContainerBindingConflictError(
                connection_ref=resource.connection_ref,
                container_name=spec.name,
                logical_id=resource.logical_id,
                conflicting_logical_id=conflicting_logical_id,
            )
        owners[physical_key] = resource.logical_id
        grouped.setdefault(resource.connection_ref, []).append((resource.logical_id, spec))

    prepared: list[tuple[CosmosProvisioner, tuple[CosmosContainerSpec, ...]]] = []
    for connection_ref in sorted(grouped):
        if connection_ref not in provisioners:
            raise MissingCosmosProvisionerError(connection_ref=connection_ref)
        provisioner = provisioners[connection_ref]
        if not isinstance(provisioner, CosmosProvisioner):
            raise InvalidCosmosProvisionerError(connection_ref=connection_ref)
        specs = tuple(spec for _, spec in grouped[connection_ref])
        prepared.append((provisioner, specs))

    return tuple(prepared)
