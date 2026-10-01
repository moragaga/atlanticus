from __future__ import annotations

from dataclasses import replace

import pytest
from flask import Flask

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
from atlanticus.web.users.local import LOCAL_ISSUER
from atlanticus.web.users.models import EffectiveUser
from atlanticus.web.users.runtime import UsersRuntime


def _access(
    *,
    bootstrap_root: bool = False,
    provider_key: str = 'local',
    issuer: str = 'issuer-1',
    subject_id: str = 'subject-1',
) -> AccessSnapshot:
    return AccessSnapshot.resolved(
        load_id='load-1',
        identity=AuthenticatedIdentity(
            provider_key=provider_key,
            issuer=issuer,
            subject_id=subject_id,
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


def test_managed_root_uses_administrative_override_without_access_keys() -> None:
    principal = resolve_manager_principal(
        access=_access(),
        user=_user(profile_key='root'),
    )

    assert principal.subject_id == 'subject-1'
    assert principal.profile_keys == ('root',)
    assert principal.access_keys == ()
    assert principal.administrative_override is True
    assert principal.is_local is False


@pytest.mark.parametrize('profile_key', ['basic', 'guest', 'custom'])
def test_non_administrative_managed_profiles_have_no_manager_access(profile_key: str) -> None:
    principal = resolve_manager_principal(
        access=_access(),
        user=_user(profile_key=profile_key),
    )

    assert principal.profile_keys == (profile_key,)
    assert principal.access_keys == ()
    assert principal.administrative_override is False


def test_authenticated_identity_without_managed_user_has_no_manager_access() -> None:
    principal = resolve_manager_principal(
        access=_access(),
        user=None,
    )

    assert principal.display_name == 'Authenticated identity'
    assert principal.profile_keys == ()
    assert principal.access_keys == ()
    assert principal.administrative_override is False
    assert principal.is_local is False


def test_bootstrap_root_does_not_implicitly_grant_manager_permissions() -> None:
    principal = resolve_manager_principal(
        access=_access(bootstrap_root=True),
        user=None,
    )

    assert principal.access_keys == ()
    assert principal.administrative_override is False
    with pytest.raises(ValueError, match='Bootstrap root'):
        resolve_manager_principal(
            access=_access(bootstrap_root=True),
            user=_user(profile_key='root'),
        )


def test_local_effective_user_requires_trusted_local_binding_for_override() -> None:
    local_user = _user(profile_key='local', is_local=True)

    principal = resolve_manager_principal(
        access=_access(),
        user=local_user,
    )

    assert principal.profile_keys == ('local',)
    assert principal.access_keys == ()
    assert principal.administrative_override is False
    assert principal.is_local is True


def test_mismatched_or_disabled_user_is_rejected() -> None:
    for user, message in (
        (replace(_user(), subject_id='different'), 'does not match'),
        (replace(_user(), enabled=False), 'Disabled user'),
    ):
        with pytest.raises(ValueError, match=message):
            resolve_manager_principal(
                access=_access(),
                user=user,
            )


def test_non_ready_identity_is_rejected() -> None:
    with pytest.raises(ValueError, match='ready authenticated access'):
        resolve_manager_principal(
            access=AccessSnapshot.invalid_identity(),
            user=None,
        )


def test_binding_reads_shared_access_and_users_snapshots_inside_request() -> None:
    app = Flask(__name__)
    app.secret_key = 'test-only-secret'
    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    binding = ManagerPrincipalBinding(
        access_runtime=access_runtime,
        users_runtime=users_runtime,
    )

    with app.test_request_context('/manager'):
        access_runtime.store(_access())
        users_runtime.store(load_id='load-1', user=_user(profile_key='root'))
        principal = binding()

    assert principal.access_keys == ()
    assert principal.administrative_override is True


def test_binding_grants_override_to_known_trusted_local_identity() -> None:
    app = Flask(__name__)
    app.secret_key = 'test-only-secret'
    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    binding = ManagerPrincipalBinding(
        access_runtime=access_runtime,
        users_runtime=users_runtime,
        trusted_local_users=True,
    )

    with app.test_request_context('/manager'):
        access_runtime.store(
            _access(
                provider_key='local',
                issuer=LOCAL_ISSUER,
                subject_id='local:jane-doe',
            )
        )
        principal = binding()

    assert principal.profile_keys == ('local',)
    assert principal.access_keys == ()
    assert principal.administrative_override is True
    assert principal.is_local is True


def test_binding_does_not_trust_local_identity_without_explicit_flag() -> None:
    app = Flask(__name__)
    app.secret_key = 'test-only-secret'
    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    binding = ManagerPrincipalBinding(
        access_runtime=access_runtime,
        users_runtime=users_runtime,
    )

    with app.test_request_context('/manager'):
        access_runtime.store(
            _access(
                provider_key='local',
                issuer=LOCAL_ISSUER,
                subject_id='local:jane-doe',
            )
        )
        principal = binding()

    assert principal.profile_keys == ()
    assert principal.access_keys == ()
    assert principal.administrative_override is False
