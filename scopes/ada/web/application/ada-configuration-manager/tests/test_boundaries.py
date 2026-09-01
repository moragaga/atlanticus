from pathlib import Path


def test_application_composition_has_no_physical_backend_or_legacy_manager_tools() -> None:
    package = (
        Path(__file__).parents[1] / 'src' / 'ada' / 'web' / 'application' / 'configuration_manager'
    )
    source = '\n'.join(path.read_text(encoding='utf-8') for path in package.rglob('*.py'))

    for forbidden in (
        'SharePoint',
        'Cosmos',
        'Databricks',
        'ServiceBus',
        'manager_tools',
        'kpi_definition.web',
    ):
        assert forbidden not in source


def test_tools_module_does_not_select_between_multiple_tools() -> None:
    package = (
        Path(__file__).parents[1] / 'src' / 'ada' / 'web' / 'application' / 'configuration_manager'
    )
    source = '\n'.join(path.read_text(encoding='utf-8') for path in package.rglob('*.py'))

    for forbidden in (
        'selected_tool',
        'default_tool',
        'tool_selector',
        'tool_catalog',
    ):
        assert forbidden not in source


def test_cl003b_exposes_users_navigation_and_single_tool_surface() -> None:
    composition = (
        Path(__file__).parents[1]
        / 'src'
        / 'ada'
        / 'web'
        / 'application'
        / 'configuration_manager'
        / 'composition.py'
    ).read_text(encoding='utf-8')

    assert "key='users'" in composition
    assert "key='navigation'" in composition
    assert "key='tools'" in composition
    assert "key='kpi-definitions'" not in composition
