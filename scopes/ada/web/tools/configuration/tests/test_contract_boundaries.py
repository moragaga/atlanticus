from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1]
SOURCE_ROOT = PACKAGE_ROOT / 'src' / 'ada' / 'web' / 'tools' / 'configuration' / 'web'


def test_editor_source_does_not_depend_on_physical_infrastructure_or_manager_application() -> None:
    source = '\n'.join(
        path.read_text(encoding='utf-8') for path in SOURCE_ROOT.rglob('*.py')
    ).casefold()

    forbidden = (
        'cosmos',
        'sharepoint',
        'service bus',
        'managerapplication',
    )
    assert not any(token in source for token in forbidden)

