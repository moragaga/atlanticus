from pathlib import Path


def test_navigation_configuration_does_not_import_users_or_ada() -> None:
    root = Path(__file__).parents[1]
    pyproject = (root / 'pyproject.toml').read_text(encoding='utf-8')
    sources = '\n'.join(
        path.read_text(encoding='utf-8') for path in sorted((root / 'src').rglob('*.py'))
    )

    assert 'atlanticus-web-users' not in pyproject
    assert 'atlanticus.web.users' not in sources
    assert 'ada.' not in sources
