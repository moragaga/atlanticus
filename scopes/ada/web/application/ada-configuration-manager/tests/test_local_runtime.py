from ada.web.application.configuration_manager.local_runtime import (
    ADA_ACCESS_SOURCE_KEY,
    KPI_DEFINITION_SOURCE_KEY,
    KPI_REGISTRY_SOURCE_KEY,
    NAVIGATION_SOURCE_KEY,
    TOOLS_SOURCE_KEY,
    create_local_configuration_manager_dependencies,
)
from atlanticus.web.compositions.navigation_manager import (
    NAVIGATION_MANAGER_PROJECTION_SERVICE,
    NAVIGATION_MANAGER_SOURCE_SERVICE,
    NAVIGATION_MANAGER_VALIDATION_SERVICE,
)
from atlanticus.web.compositions.profiles_manager import (
    PROFILES_MANAGER_PROJECTION_SERVICE,
    PROFILES_MANAGER_SOURCE_SERVICE,
    PROFILES_MANAGER_VALIDATION_SERVICE,
)
from atlanticus.web.compositions.users_manager import USERS_ADMINISTRATION_SERVICE
from atlanticus.web.services import ServiceRegistry


def test_local_runtime_composes_configuration_sources(tmp_path) -> None:
    dependencies = create_local_configuration_manager_dependencies(source_root=tmp_path)

    assert dependencies.navigation_module.key == 'navigation'
    assert dependencies.navigation_module.title == 'Navegación'
    assert dependencies.navigation_module.source_key == NAVIGATION_SOURCE_KEY
    assert dependencies.navigation_module.source_name == 'Local Source'
    assert dependencies.navigation_module.projection_name == 'In-process Projection'
    assert dependencies.tools_source.source_key == TOOLS_SOURCE_KEY
    assert dependencies.access_source.source_key == ADA_ACCESS_SOURCE_KEY
    assert dependencies.kpi_registry_source is not None
    assert dependencies.kpi_registry_source.source_key == KPI_REGISTRY_SOURCE_KEY
    assert dependencies.kpi_definitions_source is not None
    assert dependencies.kpi_definitions_source.source_key == KPI_DEFINITION_SOURCE_KEY
    assert dependencies.kpi_registry_projection_store is not None
    assert dependencies.profiles_module.key == 'profiles'
    assert dependencies.profiles_module.title == 'Perfiles'
    assert dependencies.profiles_module.description == (
        'Define los perfiles disponibles y su presentación visual dentro del sistema.'
    )
    assert dependencies.profiles_module.source_key.value == 'profiles-configuration'
    assert dependencies.profiles_module.source_name == 'Local Source'
    assert dependencies.profiles_module.projection_name == 'In-process Projection'
    assert dependencies.users_entry.key == 'users'
    assert dependencies.users_entry.route == '/users'

    services = ServiceRegistry()
    assert dependencies.navigation_module.web_module is not None
    assert dependencies.navigation_module.web_module.register_services is not None
    dependencies.navigation_module.web_module.register_services(services)
    assert services.contains(NAVIGATION_MANAGER_SOURCE_SERVICE)
    assert services.contains(NAVIGATION_MANAGER_PROJECTION_SERVICE)
    assert services.contains(NAVIGATION_MANAGER_VALIDATION_SERVICE)

    assert dependencies.profiles_module.web_module is not None
    assert dependencies.profiles_module.web_module.register_services is not None
    dependencies.profiles_module.web_module.register_services(services)
    assert services.contains(PROFILES_MANAGER_SOURCE_SERVICE)
    assert services.contains(PROFILES_MANAGER_PROJECTION_SERVICE)
    assert services.contains(PROFILES_MANAGER_VALIDATION_SERVICE)

    assert dependencies.users_entry.web_module is not None
    assert dependencies.users_entry.web_module.register_services is not None
    dependencies.users_entry.web_module.register_services(services)
    assert services.contains(USERS_ADMINISTRATION_SERVICE)


def test_local_runtime_uses_administrative_override_without_access_keys(tmp_path) -> None:
    dependencies = create_local_configuration_manager_dependencies(source_root=tmp_path)
    principal = dependencies.principal_provider()

    assert principal.is_local is True
    assert principal.profile_keys == ('local',)
    assert principal.access_keys == ()
    assert principal.administrative_override is True
