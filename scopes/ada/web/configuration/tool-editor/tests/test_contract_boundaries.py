from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1]
SOURCE_ROOT = PACKAGE_ROOT / 'src' / 'ada' / 'web' / 'configuration' / 'tool_editor'


def test_editor_source_does_not_own_persistence_or_manager_application() -> None:
    source = '\n'.join(
        path.read_text(encoding='utf-8') for path in SOURCE_ROOT.rglob('*.py')
    ).casefold()

    forbidden = (
        'cosmos',
        'sharepoint',
        'service bus',
        'managerapplication',
        'draft_owner',
        'publish(',
    )
    assert not any(token in source for token in forbidden)


def test_editor_does_not_restore_legacy_freshness_contract() -> None:
    source = '\n'.join(path.read_text(encoding='utf-8') for path in SOURCE_ROOT.rglob('*.py'))

    assert 'stale_after_seconds' not in source
    assert 'warning_after_seconds' not in source
    assert 'freshness' not in source.casefold()
