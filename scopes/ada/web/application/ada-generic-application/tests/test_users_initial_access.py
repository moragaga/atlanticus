from dataclasses import replace
from types import SimpleNamespace

import pytest
from flask import Flask

from ada.web.access.configuration import AdaAccessConfiguration
from ada.web.access.models import ProfileAccessGrant
from ada.web.application.generic.users_access import AdaInitialUsersStore
from atlanticus.web.identity.access import AccessDecision, AccessSnapshot, AccessStatus
from atlanticus.web.identity.errors import AccessResolverUnavailableError
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import (
    BASIC_PROFILE,
    ROOT_PROFILE,
    ProfileCatalog,
    ProfileDefinition,
)
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    RuntimeOperational,
    RuntimeOperationalReference,
    RuntimeProfile,
    RuntimeUser,
    UserIdentity,
)
from atlanticus.web.users.resolver import UsersAccessResolver
from atlanticus.web.users.runtime import UsersRuntime
from atlanticus.web.users.store import UsersRuntimeStore


class _RuntimeStore(UsersRuntimeStore):
    def __init__(self, user=None):
        self.user = user
        self.reads = 0

    def resolve(self, identity):
        self.reads += 1
        return self.user

    def list_users(self):
        return () if self.user is None else (self.user,)

    def replace_all(self, users):
        self.user = users[0] if users else None
        return tuple(users)


class _Projection:
    def __init__(self, record=None):
        self.record = record
        self.reads = 0

    def get_active(self, source_key):
        self.reads += 1
        return self.record


def _identity():
    return AuthenticatedIdentity(provider_key='entra', issuer='issuer', subject_id='person')


def _user(*, root=False, enabled=True):
    identity = UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id='person'),
        issuer='issuer',
        subject_id='person',
        display_name='Person',
    )
    return RuntimeUser(
        identity=identity,
        enabled=enabled,
        profile=RuntimeProfile.from_profile(ROOT_PROFILE if root else BASIC_PROFILE),
        operational=RuntimeOperational(
            position=RuntimeOperationalReference(id='operator', label='Operador'),
        ),
        access_keys=('legacy.grant',),
    )


def _projections(*, keys=('dashboard.view',)):
    profile = SimpleNamespace(payload=ProfileCatalog(), target='profiles-r1')
    access = SimpleNamespace(
        payload=AdaAccessConfiguration(
            access_keys=('dashboard.view', 'alarm.manage'),
            profile_access=(ProfileAccessGrant(profile_key='basic', access_keys=keys),),
        ),
        dependencies=('profiles-r1',),
    )
    return _Projection(profile), _Projection(access)


def _resolver(*, user=None, profiles=None, access=None):
    store = _RuntimeStore(user)
    profile_store = profiles or _Projection()
    access_store = access or _Projection()
    snapshot = UsersRuntime()
    resolver = UsersAccessResolver(
        store=AdaInitialUsersStore(
            runtime=store,
            profiles=profile_store,
            access=access_store,
        ),
        runtime=snapshot,
    )
    return resolver, snapshot, store, profile_store, access_store


def test_initial_load_resolves_fresh_access_and_preserves_operational_data():
    profiles, access = _projections()
    resolver, runtime, store, _, _ = _resolver(
        user=_user(), profiles=profiles, access=access
    )
    app = Flask(__name__)
    app.secret_key = 'test'

    with app.test_request_context('/'):
        decision = resolver.resolve(_identity(), load_id='load-1')
        snapshot = AccessSnapshot.resolved(
            load_id='load-1', identity=_identity(), decision=decision
        )
        current = runtime.current(snapshot)
        assert decision.status is AccessStatus.READY
        assert current.access_keys == ('dashboard.view',)
        assert current.operational == _user().operational
        assert current.identity == _user().identity
        assert store.user.access_keys == ('legacy.grant',)
        assert (store.reads, profiles.reads, access.reads) == (1, 1, 1)

        access.record = SimpleNamespace(
            payload=AdaAccessConfiguration(
                access_keys=('dashboard.view', 'alarm.manage'),
                profile_access=(
                    ProfileAccessGrant(profile_key='basic', access_keys=('alarm.manage',)),
                ),
            ),
            dependencies=('profiles-r1',),
        )
        assert runtime.current(snapshot).access_keys == ('dashboard.view',)
        assert (store.reads, profiles.reads, access.reads) == (1, 1, 1)

        refreshed = resolver.resolve(_identity(), load_id='load-2')
        next_snapshot = AccessSnapshot.resolved(
            load_id='load-2', identity=_identity(), decision=refreshed
        )
        assert runtime.current(next_snapshot).access_keys == ('alarm.manage',)
        assert runtime.current_or_none(snapshot) is None
        assert (store.reads, profiles.reads, access.reads) == (2, 2, 2)


def test_missing_access_projection_revokes_stale_keys_and_keeps_root_bootstrap():
    for root in (False, True):
        resolver, runtime, _, profiles, access = _resolver(user=_user(root=root))
        app = Flask(__name__)
        app.secret_key = 'test'
        with app.test_request_context('/'):
            decision = resolver.resolve(_identity(), load_id='load-1')
            snapshot = AccessSnapshot.resolved(
                load_id='load-1', identity=_identity(), decision=decision
            )
            user = runtime.current(snapshot)
            assert user.access_keys == ()
            assert user.profile.id == ('root' if root else 'basic')
            assert profiles.reads == access.reads == 1


def test_incompatible_access_projection_fails_closed():
    profiles, access = _projections()
    access.record.dependencies = ('obsolete',)
    resolver, runtime, _, _, _ = _resolver(user=_user(), profiles=profiles, access=access)
    app = Flask(__name__)
    app.secret_key = 'test'
    with app.test_request_context('/'):
        with pytest.raises(AccessResolverUnavailableError):
            resolver.resolve(_identity(), load_id='load-1')
        assert runtime.current_or_none(
            AccessSnapshot.resolved(
                load_id='load-1', identity=_identity(),
                decision=AccessDecision(status=AccessStatus.READY),
            )
        ) is None


def test_disabled_and_unknown_users_do_not_require_access_projection():
    for user, expected in ((_user(enabled=False), AccessStatus.USER_DISABLED), (None, AccessStatus.READY)):
        resolver, _, store, profiles, access = _resolver(user=user)
        app = Flask(__name__)
        app.secret_key = 'test'
        with app.test_request_context('/'):
            assert resolver.resolve(_identity(), load_id='load-1').status is expected
            assert store.reads == 1
            assert profiles.reads == access.reads == 0


def test_initial_load_refreshes_profile_presentation_from_profiles_projection():
    custom = ProfileDefinition(key='custom', label='Ingeniería', background_color='#123456')
    catalog = ProfileCatalog(profiles=(custom,))
    profiles = _Projection(SimpleNamespace(payload=catalog, target='profiles-r1'))
    access = _Projection(
        SimpleNamespace(
            payload=AdaAccessConfiguration(
                access_keys=('alarms.manage',),
                profile_access=(
                    ProfileAccessGrant(profile_key='custom', access_keys=('alarms.manage',)),
                ),
            ),
            dependencies=('profiles-r1',),
        )
    )
    stale = replace(_user(), profile=RuntimeProfile(
        id='custom', label='Antiguo', background_color='#445566', text_color='#FFFFFF'
    ))
    resolver, runtime, _, _, _ = _resolver(user=stale, profiles=profiles, access=access)
    app = Flask(__name__)
    app.secret_key = 'test'
    with app.test_request_context('/'):
        decision = resolver.resolve(_identity(), load_id='load-1')
        snapshot = AccessSnapshot.resolved(
            load_id='load-1', identity=_identity(), decision=decision
        )
        current = runtime.current(snapshot)
        assert current.profile.label == 'Ingeniería'
        assert current.profile.background_color == '#123456'
        assert current.access_keys == ('alarms.manage',)
        assert current.operational == stale.operational


def test_missing_custom_profile_fails_closed_instead_of_using_stale_details():
    stale = replace(_user(), profile=RuntimeProfile(
        id='custom', label='Anterior', background_color='#123456', text_color='#FFFFFF'
    ))
    resolver, _, _, _, _ = _resolver(user=stale)
    app = Flask(__name__)
    app.secret_key = 'test'
    with app.test_request_context('/'):
        with pytest.raises(AccessResolverUnavailableError):
            resolver.resolve(_identity(), load_id='load-1')
