from pathlib import Path


def test_manager_registers_only_workflows_owned_by_surface_modules() -> None:
    package = (
        Path(__file__).parents[1] / 'src' / 'ada' / 'web' / 'application' / 'configuration_manager'
    )
    source = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in (
            package / '__init__.py',
            package / 'composition.py',
            package / 'dependencies.py',
            package / 'workflows.py',
        )
    )

    assert 'KPI_DEFINITIONS_WORKFLOW_SERVICE' not in source
    assert 'KpiDefinitionManagerWorkflowAdapter' not in source
    assert 'kpi_definitions:' not in source


def test_kpi_composition_bridges_remain_available_without_dormant_manager_workflow() -> None:
    package = (
        Path(__file__).parents[1] / 'src' / 'ada' / 'web' / 'application' / 'configuration_manager'
    )

    assert (package / 'kpi_authority.py').is_file()
    assert (package / 'tool_kpi_destinations.py').is_file()
