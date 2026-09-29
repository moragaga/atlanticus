from ada_command_center.web.tools.catalog_manager import (
    TOOL_CATALOG_ACCESS_KEY,
    create_tool_catalog_manager_entry,
)
from atlanticus.web.manager import ManagerPrincipal


def test_catalog_entry_uses_host_group_and_independent_permission() -> None:
    principal = ManagerPrincipal('local', 'Local', access_keys=(TOOL_CATALOG_ACCESS_KEY,))
    entry = create_tool_catalog_manager_entry(
        manager=object(),
        principal_provider=lambda: principal,
        group_key='custom',
    )
    assert entry.key == 'tool-catalog'
    assert entry.group_key == 'custom'
    assert entry.route == '/tool-catalog'
    assert entry.access_key == TOOL_CATALOG_ACCESS_KEY
    assert entry.web_module is not None
    assert callable(entry.web_module.register_callbacks)
