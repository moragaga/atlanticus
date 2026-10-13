import pytest

from atlanticus.web.storage.topology import (
    CosmosContainerTopology,
    ForbiddenStorageResourceOverrideError,
    MissingStorageConnectionBindingError,
    StorageResourceOverride,
    StorageResourceOverrideField,
    resolve_storage_plan,
)
from atlanticus.web.users.activity import (
    USER_ACTIVITY_STORAGE_RESOURCE,
    USER_ACTIVITY_STORAGE_RESOURCES,
)
from atlanticus.web.users.activity.models import USER_ACTIVITY_PARTITION_KEY_PATH


def test_activity_resolves_dedicated_cosmos_container_with_renewable_day_ttl() -> None:
    plan = resolve_storage_plan(
        USER_ACTIVITY_STORAGE_RESOURCES,
        (StorageResourceOverride('users.activity', connection_ref='tracking'),),
    )
    resource, = plan.resources

    assert resource.logical_id == 'users.activity'
    assert resource.owner == 'users'
    assert resource.provider == 'cosmos'
    assert resource.connection_ref == 'tracking'
    assert resource.physical_name == 'users-activity'
    assert resource.topology == CosmosContainerTopology(
        partition_key_path=USER_ACTIVITY_PARTITION_KEY_PATH,
        default_ttl_seconds=24 * 60 * 60,
    )
    assert USER_ACTIVITY_PARTITION_KEY_PATH == '/partition_key'


def test_activity_requires_named_connection_and_forbids_physical_override() -> None:
    assert USER_ACTIVITY_STORAGE_RESOURCES == (USER_ACTIVITY_STORAGE_RESOURCE,)
    assert USER_ACTIVITY_STORAGE_RESOURCE.allowed_overrides == frozenset(
        {StorageResourceOverrideField.CONNECTION_REF}
    )
    with pytest.raises(MissingStorageConnectionBindingError):
        resolve_storage_plan(USER_ACTIVITY_STORAGE_RESOURCES)
    with pytest.raises(ForbiddenStorageResourceOverrideError):
        resolve_storage_plan(
            USER_ACTIVITY_STORAGE_RESOURCES,
            (StorageResourceOverride(
                logical_id='users.activity',
                connection_ref='tracking',
                physical_name='users-runtime',
            ),),
        )
