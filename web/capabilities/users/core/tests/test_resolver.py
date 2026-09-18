import pytest
from flask import Flask

from atlanticus.web.identity.access import AccessStatus
from atlanticus.web.identity.errors import AccessResolverUnavailableError
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.authority import BASIC_AUTHORITY_KEY
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


def _identity() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        provider_key='entra',
        issuer='entra',
        subject_id='oid-1',
        display_name='Unknown User',
        email='unknown@example.com',
    )


def _managed(*, enabled: bool = True) -> UserRecord:
    return UserRecord(
        user_id=build_user_key(issuer='entra', subject_id='oid-1'),
        issuer='entra',
        subject_id='oid-1',
        display_name='Managed User',
        email='managed@example.com',
        enabled=enabled,
        authority_key=BASIC_AUTHORITY_KEY,
    )


def test_absent_identity_is_not_promoted_and_login_performs_no_write() -> None:
    store = MemoryRuntimeStore(resolved=None)
    resolver = UsersAccessResolver(store=store, runtime=UsersRuntime())

    decision = resolver.resolve(_identity(), load_id='load-1')

    assert decision.status is AccessStatus.USER_NOT_PROMOTED
    assert decision.user_id == build_user_key(issuer='entra', subject_id='oid-1')
    assert store.resolve_calls == 1
    assert not hasattr(store, 'observe')


def test_promoted_identity_resolves_ready() -> None:
    store = MemoryRuntimeStore(resolved=_managed())
    resolver = UsersAccessResolver(store=store, runtime=UsersRuntime())

    server = Flask(__name__)
    server.secret_key = 'test-only'
    with server.test_request_context('/'):
        decision = resolver.resolve(_identity(), load_id='load-1')

    assert decision.status is AccessStatus.READY
    assert decision.user_id == _managed().user_id


def test_disabled_promoted_user_is_rejected() -> None:
    resolver = UsersAccessResolver(
        store=MemoryRuntimeStore(resolved=_managed(enabled=False)),
        runtime=UsersRuntime(),
    )

    decision = resolver.resolve(_identity(), load_id='load-1')

    assert decision.status is AccessStatus.USER_DISABLED


def test_runtime_store_failure_is_reported_as_unavailable() -> None:
    resolver = UsersAccessResolver(
        store=MemoryRuntimeStore(
            resolved=None,
            error=UsersStoreUnavailableError('unavailable'),
        ),
        runtime=UsersRuntime(),
    )

    with pytest.raises(AccessResolverUnavailableError, match='Users runtime store is unavailable'):
        resolver.resolve(_identity(), load_id='load-1')
