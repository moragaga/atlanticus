from atlanticus.web.manager import ManagerModule, ManagerModuleGroup, ManagerModuleRegistry
from atlanticus.web.manager.projection import ProjectionState
from atlanticus.web.manager.web.home import build_home_page_content
from atlanticus.web.source.models import SourceKey


def _module(key: str, order: int) -> ManagerModule:
    return ManagerModule(
        key=key,
        group_key='configuration',
        title=key.title(),
        route=f'/{key}',
        order=order,
        layout=lambda _services: None,
        source_key=SourceKey(key),
        source_service=f'{key}.source',
        source_reader_service=f'{key}.reader',
        projection_service=f'{key}.projection',
        draft_validation_service=f'{key}.validation',
    )


def test_home_page_uses_registry_order_with_generic_modules() -> None:
    modules = (_module('tools', 10), _module('kpis', 20))
    registry = ManagerModuleRegistry((ManagerModuleGroup('configuration', 'Configuraciones', 10),), modules)

    content = build_home_page_content(
        registry=registry,
        modules=registry.modules,
        states={'tools': ProjectionState.SYNCHRONIZED, 'kpis': ProjectionState.READY},
        page=1,
    )

    assert len(content) == 5
