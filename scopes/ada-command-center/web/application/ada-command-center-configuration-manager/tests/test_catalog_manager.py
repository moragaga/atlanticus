from ada_command_center.web.application.configuration_manager.catalog_manager import (
    TOOL_CATALOG_ACCESS_KEY,
    create_tool_catalog_manager_entry,
)
from atlanticus.web.manager import ManagerPrincipal


def test_catalog_admin_entry_requires_independent_permission() -> None:
    principal = ManagerPrincipal('local', 'Local', access_keys=(TOOL_CATALOG_ACCESS_KEY,))
    entry = create_tool_catalog_manager_entry(
        manager=object(), principal_provider=lambda: principal
    )
    assert entry.key == 'tool-catalog'
    assert entry.route == '/tool-catalog'
    assert entry.access_key == TOOL_CATALOG_ACCESS_KEY
    assert entry.web_module is not None
    assert callable(entry.web_module.register_callbacks)
