from pathlib import Path

import ada.web.tools.configuration as configuration


def test_tools_configuration_headless_layer_has_no_manager_or_physical_adapter_dependency() -> None:
    package = Path(configuration.__file__).parent
    source = '\n'.join(path.read_text(encoding='utf-8') for path in package.glob('*.py'))

    for forbidden in (
        'atlanticus.web.manager',
        'SharePoint',
        'Cosmos',
        'dash',
        'flask',
    ):
        assert forbidden not in source
