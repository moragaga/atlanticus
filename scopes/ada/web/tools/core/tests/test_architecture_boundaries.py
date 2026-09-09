from pathlib import Path

import ada.web.tools
from ada.web.tools import enums, errors, structure


def test_tools_parent_is_namespace_package() -> None:
    assert ada.web.tools.__spec__ is not None
    assert ada.web.tools.__spec__.submodule_search_locations is not None
    assert getattr(ada.web.tools, '__file__', None) is None


def test_core_contracts_live_in_owning_modules() -> None:
    assert hasattr(enums, 'ToolConfigurationKind')
    assert hasattr(errors, 'ToolConfigurationValidationError')
    assert hasattr(structure, 'ToolStructure')


def test_core_has_no_configuration_branding_or_web_runtime_dependency() -> None:
    root = Path(structure.__file__).parent
    source = '\n'.join(path.read_text(encoding='utf-8') for path in root.glob('*.py'))
    for forbidden in (
        'ada.web.tools.configuration',
        'ada.web.branding',
        'atlanticus.web',
        'dash',
        'flask',
    ):
        assert forbidden not in source
