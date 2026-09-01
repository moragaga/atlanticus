from ada.web.application.configuration_manager import (
    create_configuration_manager_web_definition,
)

from .test_composition import dependencies


def test_web_definition_mounts_manager_pages_and_surface_modules() -> None:
    definition = create_configuration_manager_web_definition(dependencies())

    assert definition.metadata.application_id == 'ada-configuration-manager'
    assert definition.metadata.display_name == 'ADA Configuration Manager'
    assert definition.page_packages == ('ada.web.application.configuration_manager.pages',)

    module_names = tuple(module.name for module in definition.modules)
    assert 'ada-configuration-manager-services' in module_names
    assert 'manager-surface' in module_names
