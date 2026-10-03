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
from atlanticus.web.profiles.models import BASIC_PROFILE, LOCAL_PROFILE, ROOT_PROFILE, ProfileDefinition
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.local import LOCAL_ISSUER
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity
from atlanticus.web.users.runtime import UsersRuntime


def _access(
    *,
    bootstrap_root=False,
    provider_key='local',
    issuer='issuer-1',
    subject_id='subject-1',
):
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


def _user(*, profile='basic', enabled=True, issuer='issuer-1', subject_id='subject-1'):
    profiles = {
        'basic': BASIC_PROFILE,
        'root': ROOT_PROFILE,
        'local': LOCAL_PROFILE,
        'custom': ProfileDefinition(
            key='custom',
            label='Custom',
            background_color='#123456',
        ),
    }
    identity = UserIdentity(
        user_id=build_user_key(issuer=issuer, subject_id=subject_id),
        issuer=issuer,
        subject_id=subject_id,
        display_name='Managed user',
    )
    return RuntimeUser(
        identity=identity,
        enabled=enabled,
        profile=RuntimeProfile.from_profile(profiles[profile]),
    )


def test_root_runtime_user_gets_administrative_override_and_profile_presentation():
    principal = resolve_manager_principal(access=_access(), user=_user(profile='root'))
    assert principal.profile_keys == ('root',)
    assert principal.administrative_override is True
    assert principal.profile_label == ROOT_PROFILE.label
    assert principal.profile_background_color == ROOT_PROFILE.background_color


@pytest.mark.parametrize('profile', ['basic', 'custom'])
def test_non_root_runtime_profiles_do_not_get_administrative_override(profile):
    principal = resolve_manager_principal(access=_access(), user=_user(profile=profile))
    assert principal.profile_keys == (profile,)
    assert principal.administrative_override is False


def test_authenticated_identity_without_runtime_user_has_no_manager_profile():
    principal = resolve_manager_principal(access=_access(), user=None)
    assert principal.profile_keys == ()
    assert principal.administrative_override is False


def test_disabled_or_mismatched_runtime_user_is_rejected():
    with pytest.raises(ValueError, match='Disabled user'):
        resolve_manager_principal(access=_access(), user=_user(enabled=False))
    with pytest.raises(ValueError, match='does not match'):
        resolve_manager_principal(
            access=_access(),
            user=_user(subject_id='different'),
        )


def test_binding_reads_runtime_user_snapshot_inside_request():
    app = Flask(__name__)
    app.secret_key = 'test'
    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    binding = ManagerPrincipalBinding(
        access_runtime=access_runtime,
        users_runtime=users_runtime,
    )
    with app.test_request_context('/manager'):
        access_runtime.store(_access())
        users_runtime.store(load_id='load-1', user=_user(profile='root'))
        principal = binding()
    assert principal.administrative_override is True


def test_trusted_local_identity_can_bootstrap_local_principal_without_persisted_runtime_user():
    app = Flask(__name__)
    app.secret_key = 'test'
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
    assert principal.is_local is True
    assert principal.profile_keys == ('local',)
    assert principal.administrative_override is True
