from pathlib import Path

ROOT = Path(__file__).parents[1] / 'src' / 'ada' / 'web' / 'kpis' / 'configuration'
DOMAIN_FILES = tuple(ROOT.glob('*.py'))


def test_domain_has_no_physical_infrastructure_or_web_dependency() -> None:
    source = '\n'.join(path.read_text(encoding='utf-8') for path in DOMAIN_FILES).casefold()
    for forbidden in (
        'cosmos',
        'sharepoint',
        'dash',
        'flask',
        'service bus',
        'databricks',
    ):
        assert forbidden not in source


def test_domain_does_not_import_tool_or_definition_implementation() -> None:
    source = '\n'.join(path.read_text(encoding='utf-8') for path in DOMAIN_FILES)
    assert 'ada.web.tools' not in source
    assert 'ada.web.kpis.definition' not in source
