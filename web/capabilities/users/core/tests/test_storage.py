import pytest

from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    ForbiddenStorageResourceOverrideError,
    MissingStorageConnectionBindingError,
    StorageResourceOverride,
    StorageResourceOverrideField,
    resolve_storage_plan,
)
from atlanticus.web.users.storage import (
    USERS_RUNTIME_STORAGE_RESOURCE,
    USERS_RUNTIME_STORAGE_RESOURCES,
    USERS_SUPPORT_STORAGE_RESOURCE,
    USERS_SUPPORT_STORAGE_RESOURCES,
)


def test_users_runtime_storage_contract_declares_cosmos_runtime_resource() -> None:
    contract = USERS_RUNTIME_STORAGE_RESOURCE

    assert USERS_RUNTIME_STORAGE_RESOURCES == (contract,)
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


def test_users_support_storage_contract_declares_shared_cosmos_resource() -> None:
    contract = USERS_SUPPORT_STORAGE_RESOURCE

    assert USERS_SUPPORT_STORAGE_RESOURCES == (contract,)
    assert contract.logical_id == 'users.support'
    assert contract.owner == 'users'
    assert contract.provider == 'cosmos'
    assert contract.default_connection_ref is None
    assert contract.default_physical_name == 'users-support'
    assert contract.topology == CosmosContainerTopology(
        partition_key_path='/partition_key',
        default_ttl_seconds=None,
    )
    assert contract.allowed_overrides == frozenset({StorageResourceOverrideField.CONNECTION_REF})


def test_users_storage_requires_composition_connection_bindings() -> None:
    with pytest.raises(MissingStorageConnectionBindingError):
        resolve_storage_plan(
            (*USERS_RUNTIME_STORAGE_RESOURCES, *USERS_SUPPORT_STORAGE_RESOURCES)
        )


def test_users_storage_resolves_runtime_and_support_on_same_connection() -> None:
    plan = resolve_storage_plan(
        (*USERS_RUNTIME_STORAGE_RESOURCES, *USERS_SUPPORT_STORAGE_RESOURCES),
        (
            StorageResourceOverride(logical_id='users.runtime', connection_ref='primary'),
            StorageResourceOverride(logical_id='users.support', connection_ref='primary'),
        ),
    )

    resources = {resource.logical_id: resource for resource in plan.resources}
    assert set(resources) == {'users.runtime', 'users.support'}
    assert resources['users.runtime'].connection_ref == 'primary'
    assert resources['users.runtime'].physical_name == 'users-runtime'
    assert resources['users.runtime'].topology.partition_key_path == '/id'
    assert resources['users.runtime'].topology.default_ttl_seconds is None
    assert resources['users.support'].connection_ref == 'primary'
    assert resources['users.support'].physical_name == 'users-support'
    assert resources['users.support'].topology.partition_key_path == '/partition_key'
    assert resources['users.support'].topology.default_ttl_seconds is None


@pytest.mark.parametrize(
    ('logical_id', 'physical_name'),
    (
        ('users.runtime', 'other-users-runtime'),
        ('users.support', 'other-users-support'),
    ),
)
def test_users_storage_forbids_physical_name_override(
    logical_id: str,
    physical_name: str,
) -> None:
    overrides = tuple(
        StorageResourceOverride(
            logical_id=resource_id,
            connection_ref='primary',
            physical_name=physical_name if resource_id == logical_id else None,
        )
        for resource_id in ('users.runtime', 'users.support')
    )

    with pytest.raises(ForbiddenStorageResourceOverrideError):
        resolve_storage_plan(
            (*USERS_RUNTIME_STORAGE_RESOURCES, *USERS_SUPPORT_STORAGE_RESOURCES),
            overrides,
        )
