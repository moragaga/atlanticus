from pathlib import Path


def test_navigation_configuration_depends_only_on_profiles_core_contract() -> None:
    root = Path(__file__).parents[1]
    pyproject = (root / 'pyproject.toml').read_text(encoding='utf-8')
    sources = '\n'.join(
        path.read_text(encoding='utf-8') for path in sorted((root / 'src').rglob('*.py'))
    )

    assert 'atlanticus-web-profiles==0.1.0' in pyproject
    assert 'atlanticus.web.profiles.models' in sources
    assert 'atlanticus-web-profiles-configuration' not in pyproject
    assert 'atlanticus.web.profiles.configuration' not in sources
    assert 'atlanticus-web-users' not in pyproject
    assert 'atlanticus.web.users' not in sources
    assert 'ada.' not in sources
