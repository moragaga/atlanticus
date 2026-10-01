from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerEntry,
    ManagerModule,
    ManagerPrincipal,
    manager_access_granted,
)
from atlanticus.web.source.models import SourceKey


def _module(*, access_key: str | None = 'tools.manage') -> ManagerModule:
    return ManagerModule(
        key='tools',
        group_key='configuration',
        title='Tools',
        route='/tools',
        order=10,
        layout=lambda _services: None,
        source_key=SourceKey('tools'),
        source_service='tools.source',
        source_reader_service='tools.reader',
        projection_service='tools.projection',
        draft_validation_service='tools.validation',
        access_key=access_key,
    )


def _entry(*, access_key: str | None = 'users.manage') -> ManagerEntry:
    return ManagerEntry(
        key='users',
        group_key='administration',
        title='Users',
        route='/users',
        order=10,
        layout=lambda _services: None,
        access_key=access_key,
    )


def test_explicit_module_access_key_grants_manager_access() -> None:
    policy = DefaultManagerAuthorizationPolicy()
    principal = ManagerPrincipal(
        subject_id='user-1',
        display_name='User One',
        access_keys=('tools.manage',),
    )

    assert policy.can_view(principal, _module()) is True
    assert manager_access_granted(principal, 'tools.manage') is True


def test_administrative_override_grants_any_declared_manager_access_key() -> None:
    policy = DefaultManagerAuthorizationPolicy()
    principal = ManagerPrincipal(
        subject_id='root-1',
        display_name='Root User',
        administrative_override=True,
    )

    assert policy.can_view(principal, _module(access_key='future.manage')) is True
    assert policy.can_view(principal, _entry(access_key='another.manage')) is True
    assert manager_access_granted(principal, 'new-module.manage') is True


def test_administrative_override_does_not_expose_item_without_access_key() -> None:
    policy = DefaultManagerAuthorizationPolicy()
    principal = ManagerPrincipal(
        subject_id='root-1',
        display_name='Root User',
        administrative_override=True,
    )

    assert policy.can_view(principal, _module(access_key=None)) is False
    assert manager_access_granted(principal, None) is False


def test_local_context_alone_does_not_grant_manager_access() -> None:
    policy = DefaultManagerAuthorizationPolicy()
    principal = ManagerPrincipal(
        subject_id='local',
        display_name='Local',
        is_local=True,
    )

    assert policy.can_view(principal, _module()) is False


def test_profile_key_alone_does_not_grant_manager_access() -> None:
    policy = DefaultManagerAuthorizationPolicy()
    principal = ManagerPrincipal(
        subject_id='user-1',
        display_name='User One',
        profile_keys=('root',),
    )

    assert policy.can_view(principal, _module()) is False


def test_wrong_granular_access_key_is_denied() -> None:
    policy = DefaultManagerAuthorizationPolicy()
    principal = ManagerPrincipal(
        subject_id='user-1',
        display_name='User One',
        access_keys=('users.manage',),
    )

    assert policy.can_view(principal, _module()) is False
    assert manager_access_granted(principal, 'tools.manage') is False


def test_module_without_functional_access_key_is_not_exposed() -> None:
    policy = DefaultManagerAuthorizationPolicy()
    principal = ManagerPrincipal(
        subject_id='user-1',
        display_name='User One',
        access_keys=('tools.manage',),
    )

    assert policy.can_view(principal, _module(access_key=None)) is False
