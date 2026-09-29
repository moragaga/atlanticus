from dataclasses import replace

from ada_command_center.web.application.configuration_manager import (
    build_configuration_manager_surface,
)
from atlanticus.web.manager import ManagerModuleRegistry

from .test_composition import dependencies


def test_catalog_entry_is_added_only_when_service_is_injected() -> None:
    baseline = dependencies()
    without_catalog = build_configuration_manager_surface(baseline)
    assert without_catalog.entries == ()
    with_catalog = build_configuration_manager_surface(
        replace(baseline, tool_catalog_manager=object())
    )
    assert len(with_catalog.modules) == 1
    assert len(with_catalog.entries) == 1
    assert with_catalog.entries[0].access_key == 'tools.manage'
    registry = ManagerModuleRegistry(
        with_catalog.groups,
        with_catalog.modules,
        entries=with_catalog.entries,
        route_prefix=with_catalog.route_prefix,
    )
    assert registry.route_for(with_catalog.entries[0]) == '/manager/tool-catalog'
