from pathlib import Path


def test_tools_lifecycle_has_no_manager_or_physical_adapter_dependency() -> None:
    package = Path(__file__).parents[1] / 'src' / 'ada' / 'configuration' / 'tools_lifecycle'
    source = '\n'.join(path.read_text(encoding='utf-8') for path in package.rglob('*.py'))

    for forbidden in (
        'atlanticus.web.manager',
        'SharePoint',
        'Cosmos',
        'dash',
        'flask',
    ):
        assert forbidden not in source
