from __future__ import annotations

from dataclasses import replace

import pytest
from flask import Flask

from ada.web.application.generic.alarm_access import (
    ALARM_ACCESS_KEYS,
    ALARM_ACTION_INFORMATION,
    ALARM_ACTION_MANAGEMENT,
    ALARM_CARDS_VIEW,
    ALARM_MANAGEMENT_SUMMARY_VIEW,
    ALARM_STATUS_VIEW,
    ALARM_SURFACE_VIEW,
    AlarmAccessBinding,
    can_view_alarm_cards,
    deny_alarm_access,
)
from ada.web.application.generic.manager.principal import ManagerPrincipalBinding
from atlanticus.web.identity.access import (
    AccessDecision,
    AccessRuntime,
    AccessSnapshot,
    AccessStatus,
)
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import BASIC_PROFILE, GUEST_PROFILE, LOCAL_PROFILE, ROOT_PROFILE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.local import LOCAL_JANE, LOCAL_ISSUER
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity
from atlanticus.web.users.runtime import UsersRuntime


def _identity():
    return AuthenticatedIdentity(provider_key='entra', issuer='issuer', subject_id='person')


def _user(*, keys=(), profile=BASIC_PROFILE, enabled=True, subject='person'):
    return RuntimeUser(
        identity=UserIdentity(
            user_id=build_user_key(issuer='issuer', subject_id=subject),
            issuer='issuer', subject_id=subject, display_name='Person',
        ),
        enabled=enabled,
        profile=RuntimeProfile.from_profile(profile),
        access_keys=tuple(sorted(keys)),
    )


def _session(*, keys=(), profile=BASIC_PROFILE, enabled=True, decision=None,
             user=True, load_id='load-1', subject='person'):
    access = AccessRuntime()
    users = UsersRuntime()
    snapshot = AccessSnapshot.resolved(
        load_id=load_id, identity=_identity(),
        decision=decision or AccessDecision(status=AccessStatus.READY),
    )
    access.store(snapshot)
    if user:
        users.store(load_id=load_id, user=_user(
            keys=keys, profile=profile, enabled=enabled, subject=subject,
        ))
    return AlarmAccessBinding(access, users), access, users


def test_permissions_are_independent_and_default_deny():
    app = Flask(__name__)
    app.secret_key = 'test'
    assert len(ALARM_ACCESS_KEYS) == 6
    with app.test_request_context('/'):
        binding, _, _ = _session(keys=(ALARM_SURFACE_VIEW, ALARM_STATUS_VIEW))
        assert binding.allows(ALARM_SURFACE_VIEW)
        assert binding.allows(ALARM_STATUS_VIEW)
        assert not binding.allows(ALARM_CARDS_VIEW)
        assert not can_view_alarm_cards(binding.allows)
        assert not binding.allows(ALARM_ACTION_INFORMATION)
        assert not binding.allows(ALARM_ACTION_MANAGEMENT)
        assert not binding.allows(ALARM_MANAGEMENT_SUMMARY_VIEW)
        assert not deny_alarm_access(ALARM_SURFACE_VIEW)
        with pytest.raises(ValueError, match='unknown'):
            binding.allows('alarm.unknown')


def test_unrestricted_profiles_and_bootstrap_root():
    app = Flask(__name__)
    app.secret_key = 'test'
    for profile in (ROOT_PROFILE, LOCAL_PROFILE):
        with app.test_request_context('/'):
            binding, _, _ = _session(profile=profile)
            assert all(binding.allows(key) for key in ALARM_ACCESS_KEYS)
            assert can_view_alarm_cards(binding.allows)
    with app.test_request_context('/'):
        binding, _, _ = _session(
            user=False, decision=AccessDecision(status=AccessStatus.READY, bootstrap_root=True),
        )
        assert all(binding.allows(key) for key in ALARM_ACCESS_KEYS)
        assert can_view_alarm_cards(binding.allows)


def test_missing_disabled_mismatched_and_stale_users_are_denied():
    app = Flask(__name__)
    app.secret_key = 'test'
    with app.test_request_context('/'):
        binding, _, _ = _session(user=False)
        assert not binding.allows(ALARM_SURFACE_VIEW)
    with app.test_request_context('/'):
        binding, _, _ = _session(keys=(ALARM_SURFACE_VIEW,), enabled=False)
        assert not binding.allows(ALARM_SURFACE_VIEW)
    with app.test_request_context('/'):
        binding, _, _ = _session(keys=(ALARM_SURFACE_VIEW,), subject='someone-else')
        assert not binding.allows(ALARM_SURFACE_VIEW)
    with app.test_request_context('/'):
        binding, access, users = _session(keys=(ALARM_SURFACE_VIEW,))
        access.store(AccessSnapshot.resolved(
            load_id='load-2', identity=_identity(),
            decision=AccessDecision(status=AccessStatus.READY),
        ))
        assert not binding.allows(ALARM_SURFACE_VIEW)
        users.store(load_id='load-2', user=_user(keys=(ALARM_SURFACE_VIEW,)))
        assert binding.allows(ALARM_SURFACE_VIEW)


@pytest.mark.parametrize(
    ('access_keys', 'expected'),
    (
        ((), False),
        ((ALARM_SURFACE_VIEW,), False),
        ((ALARM_CARDS_VIEW,), False),
        ((ALARM_SURFACE_VIEW, ALARM_CARDS_VIEW), True),
    ),
)
def test_cards_require_both_permissions(access_keys, expected):
    app = Flask(__name__)
    app.secret_key = 'test'
    with app.test_request_context('/'):
        binding, _, _ = _session(keys=access_keys)
        assert can_view_alarm_cards(binding.allows) is expected


def _local_alarm_access(*, trusted=True, known=True, guest=False, disabled=False):
    access = AccessRuntime()
    users = UsersRuntime()
    identity = AuthenticatedIdentity(
        provider_key='local',
        issuer=LOCAL_ISSUER,
        subject_id=(LOCAL_JANE.subject_id if known else 'local:unknown'),
    )
    access.store(AccessSnapshot.resolved(
        load_id='local-load', identity=identity,
        decision=AccessDecision(status=AccessStatus.READY),
    ))
    if guest or disabled:
        user = LOCAL_JANE.to_runtime_user()
        if not known:
            user = replace(user, identity=replace(
                user.identity,
                user_id=build_user_key(issuer=LOCAL_ISSUER, subject_id='local:unknown'),
                subject_id='local:unknown',
            ))
        if guest:
            user = replace(user, profile=RuntimeProfile.from_profile(GUEST_PROFILE))
        if disabled:
            user = replace(user, enabled=False)
        users.store(load_id='local-load', user=user)
    principal = ManagerPrincipalBinding(
        access_runtime=access,
        users_runtime=users,
        trusted_local_users=trusted,
    )
    return AlarmAccessBinding(
        access, users,
        trusted_local_principal=principal if trusted else None,
    )


@pytest.mark.parametrize('guest', [False, True])
def test_known_trusted_local_has_full_alarm_access_without_materialized_local_profile(guest):
    app = Flask(__name__)
    app.secret_key = 'test'
    with app.test_request_context('/'):
        binding = _local_alarm_access(guest=guest)
        assert all(binding.allows(key) for key in ALARM_ACCESS_KEYS)
        assert can_view_alarm_cards(binding.allows)


@pytest.mark.parametrize('case', [
    {'trusted': False},
    {'known': False},
    {'disabled': True},
])
def test_untrusted_unknown_or_disabled_local_identity_cannot_bypass_alarm_access(case):
    app = Flask(__name__)
    app.secret_key = 'test'
    with app.test_request_context('/'):
        binding = _local_alarm_access(**case)
        assert all(not binding.allows(key) for key in ALARM_ACCESS_KEYS)
        assert not can_view_alarm_cards(binding.allows)


def test_trusted_local_callback_cannot_authorize_different_subject():
    app = Flask(__name__)
    app.secret_key = 'test'
    with app.test_request_context('/'):
        binding = _local_alarm_access()
        principal = ManagerPrincipalBinding(
            access_runtime=binding.access_runtime,
            users_runtime=binding.users_runtime,
            trusted_local_users=True,
        )()
        fake = replace(principal, subject_id='local:someone-else')
        other = AlarmAccessBinding(
            binding.access_runtime,
            binding.users_runtime,
            trusted_local_principal=lambda: fake,
        )
        assert not other.allows(ALARM_SURFACE_VIEW)


def test_without_request_no_permissions():
    binding = AlarmAccessBinding(AccessRuntime(), UsersRuntime())
    assert all(not binding.allows(key) for key in ALARM_ACCESS_KEYS)
    assert not can_view_alarm_cards(binding.allows)
