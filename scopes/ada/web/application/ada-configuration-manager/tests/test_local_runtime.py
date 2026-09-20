from ada.web.application.configuration_manager.access import ACCESS_MANAGER_ACCESS_KEY
from ada.web.application.configuration_manager.composition import (
    KPI_MANAGER_ACCESS_KEY,
    NAVIGATION_MANAGER_ACCESS_KEY,
    PROFILES_MANAGER_ACCESS_KEY,
    TOOLS_MANAGER_ACCESS_KEY,
    USERS_MANAGER_ACCESS_KEY,
)
from ada.web.application.configuration_manager.local_runtime import (
    ADA_ACCESS_SOURCE_KEY,
    KPI_DEFINITION_SOURCE_KEY,
    KPI_SOURCE_KEY,
    NAVIGATION_SOURCE_KEY,
    TOOLS_SOURCE_KEY,
    create_local_configuration_manager_dependencies,
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

    assert dependencies.navigation_source.source_key == NAVIGATION_SOURCE_KEY
    assert dependencies.tools_source.source_key == TOOLS_SOURCE_KEY
    assert dependencies.access_source.source_key == ADA_ACCESS_SOURCE_KEY
    assert dependencies.kpis_source is not None
    assert dependencies.kpis_source.source_key == KPI_SOURCE_KEY
    assert dependencies.kpi_definitions_source is not None
    assert dependencies.kpi_definitions_source.source_key == KPI_DEFINITION_SOURCE_KEY
    assert dependencies.kpi_configuration_projection is not None
    assert dependencies.profiles_module.key == 'profiles'
    assert dependencies.profiles_module.title == 'Perfiles'
    assert dependencies.profiles_module.source_key.value == 'profiles-configuration'
    assert dependencies.users_entry.key == 'users'
    assert dependencies.users_entry.route == '/users'

    services = ServiceRegistry()
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


def test_local_runtime_grants_explicit_configuration_capabilities(tmp_path) -> None:
    dependencies = create_local_configuration_manager_dependencies(source_root=tmp_path)
    principal = dependencies.principal_provider()

    assert principal.is_local is True
    assert principal.profile_keys == ()
    assert principal.access_keys == (
        USERS_MANAGER_ACCESS_KEY,
        PROFILES_MANAGER_ACCESS_KEY,
        ACCESS_MANAGER_ACCESS_KEY,
        NAVIGATION_MANAGER_ACCESS_KEY,
        TOOLS_MANAGER_ACCESS_KEY,
        KPI_MANAGER_ACCESS_KEY,
    )
