from __future__ import annotations

from flask import Flask

from atlanticus.web.identity.access import AccessSnapshot, AccessStatus
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import GUEST_PROFILE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.local import LOCAL_ISSUER, LOCAL_JANE
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity
from atlanticus.web.users.resolver import UsersAccessResolver
from atlanticus.web.users.runtime import UsersRuntime
from atlanticus.web.users.store import UsersGuestObserver, UsersRuntimeStore


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


class Observer(UsersGuestObserver):
    def __init__(self, user):
        self.user = user
        self.calls = 0

    def observe_guest(self, identity):
        self.calls += 1
        return self.user


def test_missing_identity_is_observed_and_stored_in_session():
    identity = AuthenticatedIdentity(provider_key='entra', issuer='tenant', subject_id='alice')
    guest = RuntimeUser(
        identity=UserIdentity(
            user_id=build_user_key(issuer='tenant', subject_id='alice'),
            issuer='tenant', subject_id='alice', display_name='Alice',
        ),
        enabled=True, profile=RuntimeProfile.from_profile(GUEST_PROFILE),
    )
    observer = Observer(guest)
    app = Flask(__name__)
    app.secret_key = 'test'
    runtime = UsersRuntime()
    resolver = UsersAccessResolver(store=MemoryRuntimeStore(), runtime=runtime, guest_observer=observer)
    with app.test_request_context('/'):
        decision = resolver.resolve(identity, load_id='load-guest')
        assert decision.status is AccessStatus.READY
        assert decision.user_id == guest.user_id
        snapshot = AccessSnapshot.resolved(load_id='load-guest', identity=identity, decision=decision)
        assert runtime.current(snapshot) == guest
    assert observer.calls == 1


def test_local_identity_is_not_observed_or_persisted_as_guest():
    identity = AuthenticatedIdentity(
        provider_key='local', issuer=LOCAL_ISSUER, subject_id=LOCAL_JANE.subject_id,
    )
    guest = RuntimeUser(
        identity=LOCAL_JANE.to_identity(), enabled=True,
        profile=RuntimeProfile.from_profile(GUEST_PROFILE),
    )
    observer = Observer(guest)
    runtime = UsersRuntime()
    resolver = UsersAccessResolver(
        store=MemoryRuntimeStore(), runtime=runtime, guest_observer=observer,
    )
    app = Flask(__name__)
    app.secret_key = 'test'
    with app.test_request_context('/'):
        decision = resolver.resolve(identity, load_id='local-load')
        assert decision.status is AccessStatus.READY
        assert decision.user_id == guest.user_id
        snapshot = AccessSnapshot.resolved(
            load_id='local-load', identity=identity, decision=decision,
        )
        assert runtime.current_or_none(snapshot) is None
    assert observer.calls == 0
