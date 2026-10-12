from __future__ import annotations

from dataclasses import replace

from flask import Flask

from ada.web.application.generic.manager.principal import ManagerPrincipalBinding
from atlanticus.web.identity.access import AccessDecision, AccessRuntime, AccessSnapshot, AccessStatus
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import GUEST_PROFILE
from atlanticus.web.users.local import LOCAL_ISSUER, LOCAL_JANE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile
from atlanticus.web.users.runtime import UsersRuntime


def test_trusted_local_user_keeps_admin_access_after_guest_observation():
    app = Flask(__name__)
    app.secret_key = 'test'
    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    identity = AuthenticatedIdentity(
        provider_key='local', issuer=LOCAL_ISSUER, subject_id=LOCAL_JANE.subject_id,
    )
    guest = replace(
        LOCAL_JANE.to_runtime_user(),
        profile=RuntimeProfile.from_profile(GUEST_PROFILE),
    )
    binding = ManagerPrincipalBinding(
        access_runtime=access_runtime,
        users_runtime=users_runtime,
        trusted_local_users=True,
    )
    with app.test_request_context('/'):
        access_runtime.store(
            AccessSnapshot.resolved(
                load_id='load-1', identity=identity,
                decision=AccessDecision(status=AccessStatus.READY, user_id=guest.user_id),
            )
        )
        users_runtime.store(load_id='load-1', user=guest)
        principal = binding()
        assert principal.administrative_override is True
        assert principal.is_local is True


def test_untrusted_guest_cannot_use_local_admin_override():
    app = Flask(__name__)
    app.secret_key = 'test'
    access_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    identity = AuthenticatedIdentity(
        provider_key='local', issuer=LOCAL_ISSUER, subject_id='unknown-local-subject',
    )
    guest = replace(
        LOCAL_JANE.to_runtime_user(),
        identity=replace(
            LOCAL_JANE.to_runtime_user().identity,
            user_id=build_user_key(issuer=LOCAL_ISSUER, subject_id='unknown-local-subject'),
            subject_id='unknown-local-subject',
        ),
        profile=RuntimeProfile.from_profile(GUEST_PROFILE),
    )
    binding = ManagerPrincipalBinding(
        access_runtime=access_runtime,
        users_runtime=users_runtime, trusted_local_users=True,
    )
    with app.test_request_context('/'):
        access_runtime.store(
            AccessSnapshot.resolved(
                load_id='load-1', identity=identity,
                decision=AccessDecision(status=AccessStatus.READY, user_id=guest.user_id),
            )
        )
        users_runtime.store(load_id='load-1', user=guest)
        principal = binding()
        assert principal.administrative_override is False
