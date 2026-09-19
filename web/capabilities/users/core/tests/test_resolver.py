import pytest
from flask import Flask

from atlanticus.web.identity.access import AccessDecision, AccessSnapshot, AccessStatus
from atlanticus.web.identity.errors import AccessResolverUnavailableError
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition
from atlanticus.web.users.errors import UsersStoreUnavailableError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import UserRecord
from atlanticus.web.users.resolver import UsersAccessResolver
from atlanticus.web.users.runtime import UsersRuntime
from atlanticus.web.users.store import UsersRuntimeStore


class MemoryRuntimeStore(UsersRuntimeStore):
    def __init__(self, *, resolved: UserRecord | None, error: Exception | None = None) -> None:
        self.resolved = resolved
        self.error = error
        self.resolve_calls = 0

    def resolve(self, identity: AuthenticatedIdentity) -> UserRecord | None:
        del identity
        self.resolve_calls += 1
        if self.error is not None:
            raise self.error
        return self.resolved


def _profiles() -> ProfileCatalog:
    return ProfileCatalog(
        profiles=(
            ProfileDefinition(
                key='11111111-1111-4111-8111-111111111111',
                label='Analista',
                background_color='#112233',
            ),
        )
    )


def _identity() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        provider_key='entra',
        issuer='entra',
        subject_id='oid-1',
        display_name='Unknown User',
        email='unknown@example.com',
    )


def _managed(*, enabled: bool = True, profile_key: str = 'basic') -> UserRecord:
    return UserRecord(
        user_id=build_user_key(issuer='entra', subject_id='oid-1'),
        issuer='entra',
        subject_id='oid-1',
        display_name='Managed User',
        email='managed@example.com',
        enabled=enabled,
        profile_key=profile_key,
    )


def _resolver(store: UsersRuntimeStore) -> UsersAccessResolver:
    return UsersAccessResolver(store=store, runtime=UsersRuntime(), profiles=_profiles)


def test_absent_identity_is_ready_without_promotion_or_runtime_user() -> None:
    store = MemoryRuntimeStore(resolved=None)
    runtime = UsersRuntime()
    resolver = UsersAccessResolver(store=store, runtime=runtime, profiles=_profiles)
    identity = _identity()
    server = Flask(__name__)
    server.secret_key = 'test-only'

    with server.test_request_context('/'):
        decision = resolver.resolve(identity, load_id='load-1')
        access = AccessSnapshot.resolved(
            load_id='load-1',
            identity=identity,
            decision=AccessDecision(status=decision.status, user_id=decision.user_id),
        )
        runtime_user = runtime.current_or_none(access)

    assert decision.status is AccessStatus.READY
    assert decision.user_id == build_user_key(issuer='entra', subject_id='oid-1')
    assert runtime_user is None
    assert store.resolve_calls == 1


def test_promoted_identity_resolves_configured_profile_ready() -> None:
    managed = _managed(profile_key='11111111-1111-4111-8111-111111111111')
    resolver = _resolver(MemoryRuntimeStore(resolved=managed))

    server = Flask(__name__)
    server.secret_key = 'test-only'
    with server.test_request_context('/'):
        decision = resolver.resolve(_identity(), load_id='load-1')

    assert decision.status is AccessStatus.READY
    assert decision.user_id == managed.user_id


def test_runtime_rejects_profile_missing_from_catalog() -> None:
    resolver = _resolver(MemoryRuntimeStore(resolved=_managed(profile_key='missing')))

    with pytest.raises(AccessResolverUnavailableError, match='Users runtime store is unavailable'):
        resolver.resolve(_identity(), load_id='load-1')


def test_disabled_promoted_user_is_rejected() -> None:
    resolver = _resolver(MemoryRuntimeStore(resolved=_managed(enabled=False)))

    decision = resolver.resolve(_identity(), load_id='load-1')

    assert decision.status is AccessStatus.USER_DISABLED


def test_runtime_store_failure_is_reported_as_unavailable() -> None:
    resolver = _resolver(
        MemoryRuntimeStore(
            resolved=None,
            error=UsersStoreUnavailableError('unavailable'),
        )
    )

    with pytest.raises(AccessResolverUnavailableError, match='Users runtime store is unavailable'):
        resolver.resolve(_identity(), load_id='load-1')
