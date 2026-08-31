from pathlib import Path


def test_web_configuration_does_not_depend_on_backend_configuration_or_connectivity():
    root = Path(__file__).resolve().parents[1]
    sources = '\n'.join(path.read_text(encoding='utf-8') for path in (root / 'src').rglob('*.py'))

    assert 'atlanticus.configuration' not in sources
    assert 'atlanticus.connectivity' not in sources
    assert 'key_vault' not in sources.lower()
    assert 'dotenv' not in sources.lower()


def test_initial_contract_only_contains_current_web_environment_concerns():
    settings_source = (
        Path(__file__).resolve().parents[1] / 'src/atlanticus/web/configuration/settings.py'
    ).read_text(encoding='utf-8')

    assert 'ATLANTICUS_ENVIRONMENT' in settings_source
    assert 'APPLICATION_INSIGHTS_CONNECTION_STRING' in settings_source
    assert 'ATLANTICUS_WEB_WORKERS' not in settings_source
    assert 'ATLANTICUS_WEB_THREADS' not in settings_source
    assert 'WAKE_LOCK' not in settings_source
    assert 'PAGE_READINESS' not in settings_source
    assert 'AUTO_REFRESH' not in settings_source
    assert 'PWA' not in settings_source
