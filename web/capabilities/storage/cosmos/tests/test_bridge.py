from __future__ import annotations

from dataclasses import dataclass

import pytest

from atlanticus.connectivity.cosmos import (
    CosmosConfigurationError,
    CosmosContainerSpec,
    CosmosProvisioner,
)
from atlanticus.web.storage.cosmos import (
    CosmosContainerBindingConflictError,
    CosmosStorageTopologyMismatchError,
    InvalidCosmosProvisionerError,
    MissingCosmosProvisionerError,
    ensure_cosmos_storage_plan,
    to_cosmos_container_spec,
    validate_cosmos_storage_plan,
)
from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    ResolvedStoragePlan,
    ResolvedStorageResource,
)


class RecordingProvisioner(CosmosProvisioner):
    def __init__(self) -> None:
        self.ensure_calls: list[tuple[CosmosContainerSpec, ...]] = []
        self.validate_calls: list[tuple[CosmosContainerSpec, ...]] = []

    def ensure_containers(self, specs):
        normalized = tuple(specs)
        self.ensure_calls.append(normalized)
        return tuple(spec.name for spec in normalized)

    def validate_containers(self, specs):
        self.validate_calls.append(tuple(specs))


@dataclass(frozen=True, slots=True)
class OtherTopology:
    marker: str = 'other'


def _resource(
    logical_id: str,
    *,
    connection_ref: str = 'primary',
    physical_name: str | None = None,
    topology: object | None = None,
    provider: str = 'cosmos',
) -> ResolvedStorageResource[object]:
    return ResolvedStorageResource(
        logical_id=logical_id,
        owner='tests',
        provider=provider,
        connection_ref=connection_ref,
        physical_name=physical_name or logical_id.replace('.', '-'),
        topology=topology or CosmosContainerTopology('/id'),
    )


def test_translation_preserves_physical_name_partition_key_and_ttl() -> None:
    resource = _resource(
        'users.runtime',
        physical_name='users-runtime',
        topology=CosmosContainerTopology('/id', None),
    )

    assert to_cosmos_container_spec(resource) == CosmosContainerSpec(
        name='users-runtime',
        partition_key_path='/id',
        default_ttl_seconds=None,
    )


@pytest.mark.parametrize('ttl', [None, -1, 3600])
def test_translation_preserves_all_supported_ttl_modes(ttl: int | None) -> None:
    resource = _resource(
        'test.runtime',
        topology=CosmosContainerTopology('/tenant', ttl),
    )

    assert to_cosmos_container_spec(resource).default_ttl_seconds == ttl


def test_ensure_groups_resources_by_connection_in_deterministic_order() -> None:
    secondary = RecordingProvisioner()
    primary = RecordingProvisioner()
    plan = ResolvedStoragePlan(
        resources=(
            _resource('zeta.runtime', connection_ref='secondary', physical_name='zeta'),
            _resource('beta.runtime', physical_name='beta'),
            _resource('alpha.runtime', physical_name='alpha'),
        )
    )

    ensure_cosmos_storage_plan(
        plan,
        provisioners={'secondary': secondary, 'primary': primary},
    )

    assert [[spec.name for spec in call] for call in primary.ensure_calls] == [['alpha', 'beta']]
    assert [[spec.name for spec in call] for call in secondary.ensure_calls] == [['zeta']]
    assert primary.validate_calls == []
    assert secondary.validate_calls == []


def test_validate_uses_validate_without_ensure() -> None:
    provisioner = RecordingProvisioner()
    plan = ResolvedStoragePlan(resources=(_resource('users.runtime'),))

    validate_cosmos_storage_plan(plan, provisioners={'primary': provisioner})

    assert provisioner.ensure_calls == []
    assert len(provisioner.validate_calls) == 1


def test_non_cosmos_resources_are_ignored() -> None:
    provisioner = RecordingProvisioner()
    plan = ResolvedStoragePlan(
        resources=(
            _resource(
                'blob.runtime',
                provider='storage',
                topology=OtherTopology(),
            ),
            _resource('users.runtime'),
        )
    )

    ensure_cosmos_storage_plan(plan, provisioners={'primary': provisioner})

    assert len(provisioner.ensure_calls) == 1
    assert [spec.name for spec in provisioner.ensure_calls[0]] == ['users-runtime']


def test_plan_without_cosmos_resources_is_a_noop() -> None:
    plan = ResolvedStoragePlan(
        resources=(_resource('blob.runtime', provider='storage', topology=OtherTopology()),)
    )

    ensure_cosmos_storage_plan(plan, provisioners={})
    validate_cosmos_storage_plan(plan, provisioners={})


def test_topology_mismatch_fails_before_any_provider_call() -> None:
    provisioner = RecordingProvisioner()
    plan = ResolvedStoragePlan(
        resources=(
            _resource('alpha.runtime'),
            _resource('zeta.runtime', topology=OtherTopology()),
        )
    )

    with pytest.raises(CosmosStorageTopologyMismatchError):
        ensure_cosmos_storage_plan(plan, provisioners={'primary': provisioner})

    assert provisioner.ensure_calls == []


def test_invalid_physical_name_fails_before_any_provider_call() -> None:
    provisioner = RecordingProvisioner()
    plan = ResolvedStoragePlan(
        resources=(
            _resource('alpha.runtime'),
            _resource('zeta.runtime', physical_name='invalid/name'),
        )
    )

    with pytest.raises(CosmosConfigurationError):
        ensure_cosmos_storage_plan(plan, provisioners={'primary': provisioner})

    assert provisioner.ensure_calls == []


def test_missing_provisioner_fails_before_any_provider_call() -> None:
    provisioner = RecordingProvisioner()
    plan = ResolvedStoragePlan(
        resources=(
            _resource('alpha.runtime', connection_ref='primary'),
            _resource('zeta.runtime', connection_ref='secondary'),
        )
    )

    with pytest.raises(MissingCosmosProvisionerError):
        ensure_cosmos_storage_plan(plan, provisioners={'primary': provisioner})

    assert provisioner.ensure_calls == []


def test_invalid_provisioner_fails_before_any_provider_call() -> None:
    provisioner = RecordingProvisioner()
    plan = ResolvedStoragePlan(
        resources=(
            _resource('alpha.runtime', connection_ref='primary'),
            _resource('zeta.runtime', connection_ref='secondary'),
        )
    )

    with pytest.raises(InvalidCosmosProvisionerError):
        ensure_cosmos_storage_plan(
            plan,
            provisioners={'primary': provisioner, 'secondary': object()},
        )

    assert provisioner.ensure_calls == []


def test_duplicate_container_binding_fails_before_any_provider_call() -> None:
    provisioner = RecordingProvisioner()
    plan = ResolvedStoragePlan(
        resources=(
            _resource('alpha.runtime', physical_name='shared'),
            _resource('beta.runtime', physical_name='shared'),
        )
    )

    with pytest.raises(CosmosContainerBindingConflictError):
        ensure_cosmos_storage_plan(plan, provisioners={'primary': provisioner})

    assert provisioner.ensure_calls == []
