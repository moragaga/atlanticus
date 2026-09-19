from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerModule,
    ManagerPrincipal,
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


def test_explicit_module_access_key_grants_manager_access() -> None:
    policy = DefaultManagerAuthorizationPolicy()
    principal = ManagerPrincipal(
        subject_id='user-1',
        display_name='User One',
        access_keys=('tools.manage',),
    )

    assert policy.can_view(principal, _module()) is True


def test_local_context_does_not_grant_manager_access() -> None:
    policy = DefaultManagerAuthorizationPolicy()
    principal = ManagerPrincipal(
        subject_id='local',
        display_name='Local',
        is_local=True,
    )

    assert policy.can_view(principal, _module()) is False


def test_administrator_profile_does_not_grant_manager_access() -> None:
    policy = DefaultManagerAuthorizationPolicy()
    principal = ManagerPrincipal(
        subject_id='user-1',
        display_name='User One',
        profile_keys=('administrator',),
    )

    assert policy.can_view(principal, _module()) is False


def test_module_without_functional_access_key_is_not_exposed() -> None:
    policy = DefaultManagerAuthorizationPolicy()
    principal = ManagerPrincipal(
        subject_id='user-1',
        display_name='User One',
        access_keys=('tools.manage',),
    )

    assert policy.can_view(principal, _module(access_key=None)) is False
