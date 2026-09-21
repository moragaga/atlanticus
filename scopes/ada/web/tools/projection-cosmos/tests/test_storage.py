from ada.web.tools.projection.cosmos import (
    TOOL_PROJECTION_STORAGE_RESOURCE,
    TOOL_PROJECTION_STORAGE_RESOURCES,
)
from atlanticus.web.storage.topology import StorageResourceOverrideField


def test_tool_projection_declares_shared_cosmos_storage_contract() -> None:
    resource = TOOL_PROJECTION_STORAGE_RESOURCE

    assert TOOL_PROJECTION_STORAGE_RESOURCES == (resource,)
    assert resource.logical_id == 'ada.tools.projection'
    assert resource.owner == 'ada.tools'
    assert resource.provider == 'cosmos'
    assert resource.default_connection_ref is None
    assert resource.default_physical_name == 'ada-tool-projection'
    assert resource.topology.partition_key_path == '/partition_key'
    assert resource.topology.default_ttl_seconds is None
    assert resource.allowed_overrides == frozenset({StorageResourceOverrideField.CONNECTION_REF})
