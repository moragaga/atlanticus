from pathlib import Path

import ada.web.tools.configuration as configuration


def test_headless_configuration_public_import_does_not_load_web_layer() -> None:
    package_root = Path(configuration.__file__).parent
    public_source = (package_root / '__init__.py').read_text(encoding='utf-8')

    assert 'ada.web.tools.configuration.web' not in public_source
    assert 'dash' not in public_source
    assert 'flask' not in public_source


def test_headless_configuration_modules_do_not_import_dash() -> None:
    package_root = Path(configuration.__file__).parent
    root_modules = '\n'.join(
        path.read_text(encoding='utf-8') for path in package_root.glob('*.py')
    ).casefold()

    assert 'from dash' not in root_modules
    assert 'import dash' not in root_modules


def test_internal_configuration_modules_do_not_import_public_facade() -> None:
    package_root = Path(configuration.__file__).parent

    for path in package_root.glob('*.py'):
        if path.name == '__init__.py':
            continue
        source = path.read_text(encoding='utf-8')
        assert 'from ada.web.tools.configuration import' not in source
