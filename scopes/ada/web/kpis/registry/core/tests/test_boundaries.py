from pathlib import Path

ROOT = Path(__file__).parents[1] / 'src' / 'ada' / 'web' / 'kpis' / 'registry'
DOMAIN_FILES = tuple(ROOT.glob('*.py'))


def test_registry_core_has_no_provider_or_web_dependency() -> None:
    source = '\n'.join(path.read_text(encoding='utf-8') for path in DOMAIN_FILES).casefold()
    for forbidden in (
        'cosmos',
        'sharepoint',
        'dash',
        'flask',
        'service bus',
        'databricks',
        'atlanticus.web.source',
        'atlanticus.web.projection',
    ):
        assert forbidden not in source
