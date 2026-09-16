from ada.web.application.configuration_manager.local_runtime import (
    KPI_DEFINITION_SOURCE_KEY,
    KPI_SOURCE_KEY,
    NAVIGATION_SOURCE_KEY,
    TOOLS_SOURCE_KEY,
    USERS_SOURCE_KEY,
    create_local_configuration_manager_dependencies,
)


def test_local_runtime_composes_five_independent_named_sources(tmp_path) -> None:
    dependencies = create_local_configuration_manager_dependencies(source_root=tmp_path)

    assert dependencies.users_source_key == USERS_SOURCE_KEY
    assert dependencies.navigation_source.source_key == NAVIGATION_SOURCE_KEY
    assert dependencies.tools_source.source_key == TOOLS_SOURCE_KEY
    assert dependencies.kpis_source is not None
    assert dependencies.kpis_source.source_key == KPI_SOURCE_KEY
    assert dependencies.kpi_definitions_source is not None
    assert dependencies.kpi_definitions_source.source_key == KPI_DEFINITION_SOURCE_KEY
    assert dependencies.kpi_configuration_projection is not None
