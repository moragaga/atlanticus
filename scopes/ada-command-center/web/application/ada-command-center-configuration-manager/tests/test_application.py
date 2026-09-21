from ada_command_center.web.application.configuration_manager import (
    create_configuration_manager_web_definition,
)

from .test_composition import dependencies


def test_web_definition_mounts_manager_surface_and_page_package() -> None:
    definition = create_configuration_manager_web_definition(dependencies())

    assert definition.metadata.application_id == 'ada-command-center-configuration-manager'
    assert definition.metadata.display_name == 'ADA Command Center Configuration Manager'
    assert definition.page_packages == (
        'ada_command_center.web.application.configuration_manager.pages',
    )

    module_names = tuple(module.name for module in definition.modules)
    assert 'ada-command-center-alarm-configuration' in module_names
    assert 'manager-surface' in module_names
