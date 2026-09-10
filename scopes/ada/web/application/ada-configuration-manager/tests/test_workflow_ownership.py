from pathlib import Path


def test_manager_registers_only_workflows_owned_by_surface_modules() -> None:
    package = (
        Path(__file__).parents[1] / 'src' / 'ada' / 'web' / 'application' / 'configuration_manager'
    )
    composition = (package / 'composition.py').read_text(encoding='utf-8')
    dependencies = (package / 'dependencies.py').read_text(encoding='utf-8')
    workflows = (package / 'workflows.py').read_text(encoding='utf-8')

    assert "key='kpi-definitions'" in composition
    assert 'KPI_DEFINITION_WORKFLOW_SERVICE' in composition
    assert 'KpiDefinitionManagerWorkflowAdapter' in composition
    assert 'KpiDefinitionManagerWorkflowAdapter' in workflows
    assert 'kpi_definitions:' in dependencies
    assert 'kpi_definition_authority:' in dependencies
    assert 'kpi_definitions_source_name:' in dependencies
    assert 'kpi_definitions_projection_name:' in dependencies
    assert 'KPI_DEFINITIONS_WORKFLOW_SERVICE' not in composition


def test_kpi_composition_bridges_remain_available_without_dormant_manager_workflow() -> None:
    package = (
        Path(__file__).parents[1] / 'src' / 'ada' / 'web' / 'application' / 'configuration_manager'
    )

    assert (package / 'kpi_authority.py').is_file()
    assert (package / 'tool_kpi_destinations.py').is_file()
