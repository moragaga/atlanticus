from pathlib import Path


def test_application_composition_has_no_physical_backend_or_temporary_editor_bridge() -> None:
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


def test_cl003a_exposes_only_native_manager_web_surfaces() -> None:
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
    assert "key='tools'" not in composition
    assert "key='kpi-definitions'" not in composition
