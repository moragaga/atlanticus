from ada.web.application.configuration_manager.composition import (
    KPI_MANAGER_ACCESS_KEY,
    NAVIGATION_MANAGER_ACCESS_KEY,
    TOOLS_MANAGER_ACCESS_KEY,
)
from ada.web.application.configuration_manager.local_runtime import (
    KPI_DEFINITION_SOURCE_KEY,
    KPI_SOURCE_KEY,
    NAVIGATION_SOURCE_KEY,
    TOOLS_SOURCE_KEY,
    create_local_configuration_manager_dependencies,
)


def test_local_runtime_composes_configuration_sources(tmp_path) -> None:
    dependencies = create_local_configuration_manager_dependencies(source_root=tmp_path)

    assert dependencies.navigation_source.source_key == NAVIGATION_SOURCE_KEY
    assert dependencies.tools_source.source_key == TOOLS_SOURCE_KEY
    assert dependencies.kpis_source is not None
    assert dependencies.kpis_source.source_key == KPI_SOURCE_KEY
    assert dependencies.kpi_definitions_source is not None
    assert dependencies.kpi_definitions_source.source_key == KPI_DEFINITION_SOURCE_KEY
    assert dependencies.kpi_configuration_projection is not None


def test_local_runtime_grants_explicit_configuration_capabilities(tmp_path) -> None:
    dependencies = create_local_configuration_manager_dependencies(source_root=tmp_path)
    principal = dependencies.principal_provider()

    assert principal.is_local is True
    assert principal.profile_keys == ()
    assert principal.access_keys == (
        NAVIGATION_MANAGER_ACCESS_KEY,
        TOOLS_MANAGER_ACCESS_KEY,
        KPI_MANAGER_ACCESS_KEY,
    )
