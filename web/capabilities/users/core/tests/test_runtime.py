from flask import Flask

from atlanticus.web.identity.access import AccessDecision, AccessSnapshot, AccessStatus
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import BASIC_PROFILE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity
from atlanticus.web.users.runtime import UsersRuntime, UsersSnapshot


def _identity() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        provider_key='entra',
        issuer='issuer',
        subject_id='subject',
        display_name='User',
    )


def _user() -> RuntimeUser:
    identity = UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id='subject'),
        issuer='issuer',
        subject_id='subject',
        display_name='User',
    )
    return RuntimeUser(
        identity=identity,
        enabled=True,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE),
    )


def test_users_snapshot_round_trips_complete_runtime_user():
    snapshot = UsersSnapshot(load_id='load-1', user=_user())
    assert UsersSnapshot.from_session(snapshot.to_session()) == snapshot


def test_users_runtime_is_scoped_to_access_load_id():
    app = Flask(__name__)
    app.secret_key = 'test'
    runtime = UsersRuntime()
    identity = _identity()
    ready = AccessDecision(status=AccessStatus.READY, user_id=_user().user_id)
    with app.test_request_context('/'):
        runtime.store(load_id='load-1', user=_user())
        matching = AccessSnapshot.resolved(load_id='load-1', identity=identity, decision=ready)
        stale = AccessSnapshot.resolved(load_id='load-2', identity=identity, decision=ready)
        assert runtime.current(matching) == _user()
        assert runtime.current_or_none(stale) is None
