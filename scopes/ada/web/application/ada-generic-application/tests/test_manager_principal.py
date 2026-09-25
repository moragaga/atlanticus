from __future__ import annotations

from dataclasses import replace

import pytest
from flask import Flask

from ada.web.access.configuration import AdaAccessConfiguration
from ada.web.access.models import ProfileAccessGrant
from ada.web.application.generic.manager_principal import (
    ManagerPrincipalBinding,
    resolve_manager_principal,
)
from atlanticus.web.identity.access import (
    AccessDecision,
    AccessRuntime,
    AccessSnapshot,
    AccessStatus,
)
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.users.models import EffectiveUser
from atlanticus.web.users.runtime import UsersRuntime


def _access(*, bootstrap_root: bool = False) -> AccessSnapshot:
    return AccessSnapshot.resolved(
        load_id='load-1',
        identity=AuthenticatedIdentity(
            provider_key='local',
            issuer='issuer-1',
            subject_id='subject-1',
            display_name='Authenticated identity',
        ),
        decision=AccessDecision(status=AccessStatus.READY, bootstrap_root=bootstrap_root),
    )


def _user(*, profile_key: str = 'basic', is_local: bool = False) -> EffectiveUser:
    return EffectiveUser(
        user_id='user-1',
        subject_id='subject-1',
        display_name='Managed user',
        email=None,
        enabled=True,
        avatar_text='MU',
        profile_key=profile_key,
        is_local=is_local,
    )


def _configuration() -> AdaAccessConfiguration:
    return AdaAccessConfiguration(
        access_keys=('users.manage', 'tools.manage'),
        profile_access=(ProfileAccessGrant(profile_key='basic', access_keys=('tools.manage',)),),
    )


def test_explicit_managed_profile_grants_only_declared_permissions() -> None:
    principal = resolve_manager_principal(
        access=_access(),
        user=_user(),
        configuration=_configuration(),
        profiles=ProfileCatalog(),
    )
    assert principal.subject_id == 'subject-1'
    assert principal.profile_keys == ('basic',)
    assert principal.access_keys == ('tools.manage',)
    assert principal.is_local is False


def test_missing_durable_access_or_profile_projection_fails_closed() -> None:
    for configuration, profiles in (
        (None, ProfileCatalog()),
        (_configuration(), None),
    ):
        principal = resolve_manager_principal(
            access=_access(),
            user=_user(),
            configuration=configuration,
            profiles=profiles,
        )
        assert principal.access_keys == ()


def test_authenticated_identity_without_managed_user_has_no_manager_access() -> None:
    principal = resolve_manager_principal(
        access=_access(),
        user=None,
        configuration=_configuration(),
        profiles=ProfileCatalog(),
    )
    assert principal.display_name == 'Authenticated identity'
    assert principal.profile_keys == ()
    assert principal.access_keys == ()
    assert principal.is_local is False


def test_bootstrap_root_does_not_implicitly_grant_manager_permissions() -> None:
    principal = resolve_manager_principal(
        access=_access(bootstrap_root=True),
        user=None,
        configuration=_configuration(),
        profiles=ProfileCatalog(),
    )
    assert principal.access_keys == ()
    with pytest.raises(ValueError, match='Bootstrap root'):
        resolve_manager_principal(
            access=_access(bootstrap_root=True),
            user=_user(),
            configuration=_configuration(),
            profiles=ProfileCatalog(),
        )


def test_local_profile_requires_an_explicit_effective_user_and_access_configuration() -> None:
    local_user = _user(profile_key='local', is_local=True)
    missing = resolve_manager_principal(
        access=_access(),
        user=local_user,
        configuration=None,
        profiles=ProfileCatalog(),
    )
    assert missing.access_keys == ()
    principal = resolve_manager_principal(
        access=_access(),
        user=local_user,
        configuration=_configuration(),
        profiles=ProfileCatalog(),
    )
    assert principal.is_local is True
    assert set(principal.access_keys) == {'users.manage', 'tools.manage'}


def test_mismatched_or_disabled_user_is_rejected() -> None:
    for user, message in (
        (replace(_user(), subject_id='different'), 'does not match'),
        (replace(_user(), enabled=False), 'Disabled user'),
    ):
        with pytest.raises(ValueError, match=message):
            resolve_manager_principal(
                access=_access(),
                user=user,
                configuration=_configuration(),
                profiles=ProfileCatalog(),
            )


def test_non_ready_identity_is_rejected() -> None:
    with pytest.raises(ValueError, match='ready authenticated access'):
        resolve_manager_principal(
            access=AccessSnapshot.invalid_identity(),
            user=None,
            configuration=None,
            profiles=None,
        )


def test_binding_reads_shared_access_and_users_snapshots_inside_request() -> None:
    app = Flask(__name__)
    app.secret_key = 'test-only-secret'
    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    binding = ManagerPrincipalBinding(
        access_runtime=access_runtime,
        users_runtime=users_runtime,
        configuration_provider=_configuration,
        profiles_provider=ProfileCatalog,
    )
    with app.test_request_context('/manager'):
        access_runtime.store(_access())
        users_runtime.store(load_id='load-1', user=_user())
        principal = binding()
    assert principal.access_keys == ('tools.manage',)


def test_binding_skips_projection_reads_when_no_managed_user_exists() -> None:
    app = Flask(__name__)
    app.secret_key = 'test-only-secret'
    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()

    def fail_if_called():
        raise AssertionError('Projection must not be read for unpromoted user')

    binding = ManagerPrincipalBinding(
        access_runtime=access_runtime,
        users_runtime=users_runtime,
        configuration_provider=fail_if_called,
        profiles_provider=fail_if_called,
    )
    with app.test_request_context('/manager'):
        access_runtime.store(_access())
        principal = binding()
    assert principal.access_keys == ()
