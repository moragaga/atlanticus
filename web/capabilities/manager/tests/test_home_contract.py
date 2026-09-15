from atlanticus.web.manager import ManagerModule, ManagerModuleGroup, ManagerModuleRegistry
from atlanticus.web.manager.web.home import build_manager_home
from atlanticus.web.source.models import SourceKey


def test_manager_home_builds_for_a_generic_source_projection_module() -> None:
    module = ManagerModule(
        key='tools', group_key='configuration', title='Tools', route='/tools', order=10,
        layout=lambda _services: None, source_key=SourceKey('tools'),
        source_service='tools.source', source_reader_service='tools.reader',
        projection_service='tools.projection', draft_validation_service='tools.validation',
    )
    registry = ManagerModuleRegistry((ManagerModuleGroup('configuration', 'Configuraciones', 10),), (module,))

    result = build_manager_home(registry=registry, modules=registry.modules, states={})

    assert result is not None
