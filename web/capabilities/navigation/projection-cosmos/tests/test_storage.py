from atlanticus.web.navigation.projection.cosmos import (
    NAVIGATION_PROJECTION_STORAGE_RESOURCE,
    NAVIGATION_PROJECTION_STORAGE_RESOURCES,
)
from atlanticus.web.storage.topology import StorageResourceOverrideField


def test_navigation_projection_declares_current_cosmos_storage_contract() -> None:
    resource = NAVIGATION_PROJECTION_STORAGE_RESOURCE

    assert NAVIGATION_PROJECTION_STORAGE_RESOURCES == (resource,)
    assert resource.logical_id == 'navigation.projection'
    assert resource.owner == 'navigation'
    assert resource.provider == 'cosmos'
    assert resource.default_connection_ref is None
    assert resource.default_physical_name == 'navigation-projection'
    assert resource.topology.partition_key_path == '/partition_key'
    assert resource.topology.default_ttl_seconds is None
    assert resource.allowed_overrides == frozenset(
        {StorageResourceOverrideField.CONNECTION_REF}
    )
