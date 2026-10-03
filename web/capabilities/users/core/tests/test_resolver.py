import pytest
from flask import Flask

from atlanticus.web.identity.access import AccessSnapshot, AccessStatus
from atlanticus.web.identity.errors import AccessResolverUnavailableError
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import BASIC_PROFILE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity
from atlanticus.web.users.resolver import UsersAccessResolver
from atlanticus.web.users.runtime import UsersRuntime
from atlanticus.web.users.store import UsersRuntimeStore


class MemoryRuntimeStore(UsersRuntimeStore):
    def __init__(self, user=None):
        self.user = user

    def resolve(self, identity):
        return self.user

    def list_users(self):
        return () if self.user is None else (self.user,)

    def replace_all(self, users):
        self.user = users[0] if users else None
        return tuple(users)


def _identity(subject='subject') -> AuthenticatedIdentity:
    return AuthenticatedIdentity(provider_key='entra', issuer='issuer', subject_id=subject)


def _user(subject='subject', *, enabled=True) -> RuntimeUser:
    identity = UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id=subject),
        issuer='issuer',
        subject_id=subject,
        display_name='User',
    )
    return RuntimeUser(
        identity=identity,
        enabled=enabled,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE),
    )


def test_resolver_reads_only_users_runtime_and_stores_complete_runtime_user():
    app = Flask(__name__)
    app.secret_key = 'test'
    runtime = UsersRuntime()
    resolver = UsersAccessResolver(store=MemoryRuntimeStore(_user()), runtime=runtime)
    identity = _identity()
    with app.test_request_context('/'):
        decision = resolver.resolve(identity, load_id='load-1')
        assert decision.status is AccessStatus.READY
        access = AccessSnapshot.resolved(load_id='load-1', identity=identity, decision=decision)
        assert runtime.current(access) == _user()


def test_disabled_runtime_user_is_denied_without_session_snapshot():
    app = Flask(__name__)
    app.secret_key = 'test'
    runtime = UsersRuntime()
    resolver = UsersAccessResolver(store=MemoryRuntimeStore(_user(enabled=False)), runtime=runtime)
    with app.test_request_context('/'):
        decision = resolver.resolve(_identity(), load_id='load-1')
        assert decision.status is AccessStatus.USER_DISABLED


def test_unknown_identity_is_ready_for_bootstrap_flow_without_runtime_user():
    app = Flask(__name__)
    app.secret_key = 'test'
    resolver = UsersAccessResolver(store=MemoryRuntimeStore(), runtime=UsersRuntime())
    with app.test_request_context('/'):
        decision = resolver.resolve(_identity(), load_id='load-1')
        assert decision.status is AccessStatus.READY
        assert decision.user_id == build_user_key(issuer='issuer', subject_id='subject')


def test_runtime_identity_mismatch_fails_closed():
    app = Flask(__name__)
    app.secret_key = 'test'
    resolver = UsersAccessResolver(
        store=MemoryRuntimeStore(_user(subject='other')),
        runtime=UsersRuntime(),
    )
    with app.test_request_context('/'):
        with pytest.raises(AccessResolverUnavailableError):
            resolver.resolve(_identity(), load_id='load-1')
