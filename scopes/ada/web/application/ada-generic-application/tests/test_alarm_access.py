from __future__ import annotations

from flask import Flask
import pytest

from ada.web.application.generic.alarm_access import (
    ALARM_ACCESS_KEYS,
    ALARM_ACTION_INFORMATION,
    ALARM_ACTION_MANAGEMENT,
    ALARM_MANAGEMENT_SUMMARY_VIEW,
    ALARM_STATUS_VIEW,
    ALARM_SURFACE_VIEW,
    AlarmAccessBinding,
    deny_alarm_access,
)
from atlanticus.web.identity.access import (
    AccessDecision,
    AccessRuntime,
    AccessSnapshot,
    AccessStatus,
)
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import BASIC_PROFILE, ROOT_PROFILE, LOCAL_PROFILE
from atlanticus.web.users.identity import build_user_key
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
    assert len(ALARM_ACCESS_KEYS) == 5
    with app.test_request_context('/'):
        binding, _, _ = _session(keys=(ALARM_SURFACE_VIEW, ALARM_STATUS_VIEW))
        assert binding.allows(ALARM_SURFACE_VIEW)
        assert binding.allows(ALARM_STATUS_VIEW)
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
    with app.test_request_context('/'):
        binding, _, _ = _session(
            user=False, decision=AccessDecision(status=AccessStatus.READY, bootstrap_root=True),
        )
        assert all(binding.allows(key) for key in ALARM_ACCESS_KEYS)


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


def test_without_request_no_permissions():
    binding = AlarmAccessBinding(AccessRuntime(), UsersRuntime())
    assert all(not binding.allows(key) for key in ALARM_ACCESS_KEYS)
