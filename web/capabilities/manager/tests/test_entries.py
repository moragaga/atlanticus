import pytest

from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerDefinitionError,
    ManagerEntry,
    ManagerModule,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
)
from atlanticus.web.source.models import SourceKey


def _module() -> ManagerModule:
    return ManagerModule(
        key='profiles',
        group_key='configuration',
        title='Profiles',
        route='/profiles',
        order=10,
        layout=lambda _services: None,
        source_key=SourceKey('profiles'),
        source_service='profiles.source',
        source_reader_service='profiles.reader',
        projection_service='profiles.projection',
        draft_validation_service='profiles.validation',
        access_key='profiles.manage',
    )


def _entry() -> ManagerEntry:
    return ManagerEntry(
        key='users',
        group_key='administration',
        title='Users',
        route='/users',
        order=10,
        layout=lambda _services: None,
        access_key='users.manage',
    )


def test_registry_keeps_non_projection_entries_separate_from_modules() -> None:
    registry = ManagerModuleRegistry(
        (
            ManagerModuleGroup('administration', 'Administración', 5),
            ManagerModuleGroup('configuration', 'Configuraciones', 10),
        ),
        (_module(),),
        entries=(_entry(),),
        route_prefix='/manager',
    )

    assert tuple(item.key for item in registry.items) == ('users', 'profiles')
    assert tuple(module.key for module in registry.modules) == ('profiles',)
    assert tuple(entry.key for entry in registry.entries) == ('users',)
    assert registry.find_by_route('/manager/users').key == 'users'
    assert registry.route_for(_entry()) == '/manager/users'


def test_entry_uses_same_explicit_access_contract() -> None:
    registry = ManagerModuleRegistry(
        (
            ManagerModuleGroup('administration', 'Administración', 5),
            ManagerModuleGroup('configuration', 'Configuraciones', 10),
        ),
        (_module(),),
        entries=(_entry(),),
    )
    principal = ManagerPrincipal(
        'user-1',
        'User One',
        access_keys=('users.manage',),
    )

    assert tuple(
        item.key
        for item in registry.visible_items(principal, DefaultManagerAuthorizationPolicy())
    ) == ('users',)
    assert registry.visible_modules(principal, DefaultManagerAuthorizationPolicy()) == ()


def test_registry_rejects_duplicate_contract_across_module_and_entry() -> None:
    entry = ManagerEntry(
        key='users',
        group_key='administration',
        title='Users',
        route='/profiles',
        order=10,
        layout=lambda _services: None,
        access_key='users.manage',
    )
    with pytest.raises(ManagerDefinitionError, match='route is duplicated'):
        ManagerModuleRegistry(
            (
                ManagerModuleGroup('administration', 'Administración', 5),
                ManagerModuleGroup('configuration', 'Configuraciones', 10),
            ),
            (_module(),),
            entries=(entry,),
        )
