import pytest

from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    ForbiddenStorageResourceOverrideError,
    MissingStorageConnectionBindingError,
    StorageResourceOverride,
    StorageResourceOverrideField,
    resolve_storage_plan,
)
from atlanticus.web.users.storage import USERS_RUNTIME_STORAGE_RESOURCE, USERS_STORAGE_RESOURCES


def test_users_runtime_storage_contract_is_single_durable_cosmos_resource() -> None:
    contract = USERS_RUNTIME_STORAGE_RESOURCE

    assert USERS_STORAGE_RESOURCES == (contract,)
    assert contract.logical_id == 'users.runtime'
    assert contract.owner == 'users'
    assert contract.provider == 'cosmos'
    assert contract.default_connection_ref is None
    assert contract.default_physical_name == 'users-runtime'
    assert contract.topology == CosmosContainerTopology(
        partition_key_path='/id',
        default_ttl_seconds=None,
    )
    assert contract.allowed_overrides == frozenset({StorageResourceOverrideField.CONNECTION_REF})


def test_users_runtime_storage_requires_composition_connection_binding() -> None:
    with pytest.raises(MissingStorageConnectionBindingError):
        resolve_storage_plan(USERS_STORAGE_RESOURCES)


def test_users_runtime_storage_resolves_connection_without_changing_topology() -> None:
    plan = resolve_storage_plan(
        USERS_STORAGE_RESOURCES,
        (StorageResourceOverride(logical_id='users.runtime', connection_ref='primary'),),
    )

    assert len(plan.resources) == 1
    resource = plan.resources[0]
    assert resource.connection_ref == 'primary'
    assert resource.physical_name == 'users-runtime'
    assert resource.topology.partition_key_path == '/id'
    assert resource.topology.default_ttl_seconds is None


def test_users_runtime_storage_forbids_physical_name_override() -> None:
    with pytest.raises(ForbiddenStorageResourceOverrideError):
        resolve_storage_plan(
            USERS_STORAGE_RESOURCES,
            (
                StorageResourceOverride(
                    logical_id='users.runtime',
                    connection_ref='primary',
                    physical_name='other-users-runtime',
                ),
            ),
        )
