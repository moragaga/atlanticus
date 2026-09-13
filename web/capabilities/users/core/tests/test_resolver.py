import pytest

from atlanticus.web.identity.access import AccessDecision, AccessSnapshot, AccessStatus
from atlanticus.web.identity.errors import AccessResolverUnavailableError
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.errors import (
    UsersIdentityConflictError,
    UsersRuntimeStoreUnavailableError,
)
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import PendingUserRecord, ResolvedUserRecord, RuntimeUserRecord
from atlanticus.web.users.profiles import ProfileCatalog
from atlanticus.web.users.resolver import UsersAccessResolver
from atlanticus.web.users.runtime import UsersRuntime
from atlanticus.web.users.store import UsersRuntimeStore


class MemoryRuntimeStore(UsersRuntimeStore):
    def __init__(
        self,
        *,
        resolved: RuntimeUserRecord | None,
        observed: RuntimeUserRecord | Exception | None = None,
        resolve_error: Exception | None = None,
    ) -> None:
        self.resolved = resolved
        self.observed = observed
        self.resolve_error = resolve_error
        self.resolve_calls = 0
        self.observe_calls = 0

    def resolve(self, identity: AuthenticatedIdentity) -> RuntimeUserRecord | None:
        del identity
        self.resolve_calls += 1
        if self.resolve_error is not None:
            raise self.resolve_error
        return self.resolved

    def observe(self, identity: AuthenticatedIdentity) -> RuntimeUserRecord:
        del identity
        self.observe_calls += 1
        if isinstance(self.observed, Exception):
            raise self.observed
        if self.observed is None:
            raise AssertionError('observe result was not configured')
        return self.observed


def _identity() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        provider_key='entra',
        issuer='entra',
        subject_id='oid-1',
        display_name='Unknown User',
        email='unknown@example.com',
    )


def _pending(
    *,
    issuer: str = 'entra',
    subject_id: str = 'oid-1',
) -> PendingUserRecord:
    return PendingUserRecord(
        user_id=build_user_key(issuer=issuer, subject_id=subject_id),
        issuer=issuer,
        subject_id=subject_id,
        display_name='Unknown User',
        email='unknown@example.com',
    )


def _managed(
    *,
    issuer: str = 'entra',
    subject_id: str = 'oid-1',
    enabled: bool = True,
) -> ResolvedUserRecord:
    return ResolvedUserRecord(
        user_id=build_user_key(issuer=issuer, subject_id=subject_id),
        issuer=issuer,
        subject_id=subject_id,
        display_name='Managed User',
        email='managed@example.com',
        enabled=enabled,
        profile_key='administrator',
    )


def _resolved_runtime_user(
    *,
    resolver: UsersAccessResolver,
    runtime: UsersRuntime,
    identity: AuthenticatedIdentity,
):
    from flask import Flask

    server = Flask(__name__)
    server.secret_key = 'test-only'
    with server.test_request_context('/'):
        decision = resolver.resolve(identity, load_id='load-1')
        access = AccessSnapshot.resolved(
            load_id='load-1',
            identity=identity,
            decision=AccessDecision(status=decision.status, user_id=decision.user_id),
        )
        user = runtime.current_or_none(access)
    return decision, user


def test_existing_pending_identity_becomes_guest_without_observation() -> None:
    store = MemoryRuntimeStore(resolved=_pending())
    runtime = UsersRuntime()
    resolver = UsersAccessResolver(
        store=store,
        runtime=runtime,
        profiles=ProfileCatalog(),
    )

    decision, user = _resolved_runtime_user(
        resolver=resolver,
        runtime=runtime,
        identity=_identity(),
    )

    assert decision.status is AccessStatus.READY
    assert decision.user_id == build_user_key(issuer='entra', subject_id='oid-1')
    assert user is not None
    assert user.pending is True
    assert user.profile.key == 'guest'
    assert store.resolve_calls == 1
    assert store.observe_calls == 0


def test_absent_identity_is_observed_as_pending_guest() -> None:
    store = MemoryRuntimeStore(resolved=None, observed=_pending())
    runtime = UsersRuntime()
    resolver = UsersAccessResolver(
        store=store,
        runtime=runtime,
        profiles=ProfileCatalog(),
    )

    decision, user = _resolved_runtime_user(
        resolver=resolver,
        runtime=runtime,
        identity=_identity(),
    )

    assert decision.status is AccessStatus.READY
    assert user is not None
    assert user.pending is True
    assert user.profile.key == 'guest'
    assert store.resolve_calls == 1
    assert store.observe_calls == 1


def test_concurrent_promotion_during_observation_returns_active_user() -> None:
    store = MemoryRuntimeStore(resolved=None, observed=_managed(enabled=True))
    runtime = UsersRuntime()
    resolver = UsersAccessResolver(
        store=store,
        runtime=runtime,
        profiles=ProfileCatalog(),
    )

    decision, user = _resolved_runtime_user(
        resolver=resolver,
        runtime=runtime,
        identity=_identity(),
    )

    assert decision.status is AccessStatus.READY
    assert user is not None
    assert user.pending is False
    assert user.profile.key == 'administrator'
    assert store.observe_calls == 1


def test_concurrent_disable_during_observation_returns_disabled_decision() -> None:
    store = MemoryRuntimeStore(resolved=None, observed=_managed(enabled=False))
    resolver = UsersAccessResolver(
        store=store,
        runtime=UsersRuntime(),
        profiles=ProfileCatalog(),
    )

    from flask import Flask

    server = Flask(__name__)
    server.secret_key = 'test-only'
    with server.test_request_context('/'):
        decision = resolver.resolve(_identity(), load_id='load-1')

    assert decision.status is AccessStatus.USER_DISABLED
    assert decision.user_id == build_user_key(issuer='entra', subject_id='oid-1')
    assert store.observe_calls == 1


def test_runtime_store_resolve_failure_never_becomes_guest() -> None:
    store = MemoryRuntimeStore(
        resolved=None,
        resolve_error=UsersRuntimeStoreUnavailableError('unavailable'),
    )
    resolver = UsersAccessResolver(
        store=store,
        runtime=UsersRuntime(),
        profiles=ProfileCatalog(),
    )

    from flask import Flask

    server = Flask(__name__)
    server.secret_key = 'test-only'
    with server.test_request_context('/'):
        with pytest.raises(
            AccessResolverUnavailableError,
            match='Users runtime store is unavailable',
        ):
            resolver.resolve(_identity(), load_id='load-1')

    assert store.observe_calls == 0


def test_runtime_store_observe_failure_never_becomes_guest() -> None:
    store = MemoryRuntimeStore(
        resolved=None,
        observed=UsersRuntimeStoreUnavailableError('unavailable'),
    )
    resolver = UsersAccessResolver(
        store=store,
        runtime=UsersRuntime(),
        profiles=ProfileCatalog(),
    )

    from flask import Flask

    server = Flask(__name__)
    server.secret_key = 'test-only'
    with server.test_request_context('/'):
        with pytest.raises(
            AccessResolverUnavailableError,
            match='Users runtime store is unavailable',
        ):
            resolver.resolve(_identity(), load_id='load-1')


def test_runtime_record_for_another_identity_is_rejected() -> None:
    store = MemoryRuntimeStore(
        resolved=_managed(subject_id='oid-2'),
    )
    resolver = UsersAccessResolver(
        store=store,
        runtime=UsersRuntime(),
        profiles=ProfileCatalog(),
    )

    from flask import Flask

    server = Flask(__name__)
    server.secret_key = 'test-only'
    with server.test_request_context('/'):
        with pytest.raises(
            AccessResolverUnavailableError,
            match='Users runtime store is unavailable',
        ):
            resolver.resolve(_identity(), load_id='load-1')


def test_identity_conflict_from_runtime_store_is_reported_as_unavailable() -> None:
    store = MemoryRuntimeStore(
        resolved=None,
        resolve_error=UsersIdentityConflictError('conflict'),
    )
    resolver = UsersAccessResolver(
        store=store,
        runtime=UsersRuntime(),
        profiles=ProfileCatalog(),
    )

    from flask import Flask

    server = Flask(__name__)
    server.secret_key = 'test-only'
    with server.test_request_context('/'):
        with pytest.raises(
            AccessResolverUnavailableError,
            match='Users runtime store is unavailable',
        ):
            resolver.resolve(_identity(), load_id='load-1')
