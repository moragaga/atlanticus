from pathlib import Path


def test_navigation_configuration_is_independent_from_profiles_users_and_ada() -> None:
    root = Path(__file__).parents[1]
    pyproject = (root / 'pyproject.toml').read_text(encoding='utf-8')
    sources = '\n'.join(
        path.read_text(encoding='utf-8') for path in sorted((root / 'src').rglob('*.py'))
    )

    assert 'atlanticus-web-profiles' not in pyproject
    assert 'atlanticus.web.profiles' not in sources
    assert 'atlanticus-web-users' not in pyproject
    assert 'atlanticus.web.users' not in sources
    assert 'ada.' not in sources
