import pytest

from atlanticus.web.manager import ManagerDefinitionError, ManagerModule, ManagerModuleGroup, ManagerModuleRegistry
from atlanticus.web.source.models import SourceKey


def _layout(_services):
    return None


def _module(key: str = 'tools', route: str = '/tools') -> ManagerModule:
    return ManagerModule(
        key=key,
        group_key='configuration',
        title=key.title(),
        route=route,
        order=10,
        layout=_layout,
        source_key=SourceKey(key),
        source_service=f'{key}.source',
        source_reader_service=f'{key}.reader',
        source_history_service=f'{key}.history',
        projection_service=f'{key}.projection',
        draft_validation_service=f'{key}.validation',
    )


def test_registry_accepts_only_the_generic_source_projection_contract() -> None:
    registry = ManagerModuleRegistry(
        (ManagerModuleGroup('configuration', 'Configuraciones', 10),),
        (_module(),),
    )

    module = registry.require('tools')
    assert module.source_key == SourceKey('tools')
    assert module.projection_service == 'tools.projection'


def test_registry_rejects_duplicate_routes() -> None:
    with pytest.raises(ManagerDefinitionError, match='route is duplicated'):
        ManagerModuleRegistry(
            (ManagerModuleGroup('configuration', 'Configuraciones', 10),),
            (_module('tools', '/same'), _module('kpis', '/same')),
        )
