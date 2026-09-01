import pytest

from atlanticus.web.identity.access import AccessDecision, AccessSnapshot, AccessStatus
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.models import ResolvedUserRecord
from atlanticus.web.users.profiles import ProfileCatalog
from atlanticus.web.users.resolver import UsersAccessResolver
from atlanticus.web.users.runtime import UsersRuntime
from atlanticus.web.users.source import UsersSource


class MemorySource(UsersSource):
    def __init__(self, record: ResolvedUserRecord | None) -> None:
        self.record = record
        self.calls = 0

    def resolve(self, identity: AuthenticatedIdentity) -> ResolvedUserRecord | None:
        del identity
        self.calls += 1
        return self.record


def _identity() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        provider_key='entra',
        issuer='entra',
        subject_id='oid-1',
        display_name='Unknown User',
        email='unknown@example.com',
    )


def test_unknown_authenticated_identity_becomes_pending_guest() -> None:
    from flask import Flask

    server = Flask(__name__)
    server.secret_key = 'test-only'
    profiles = ProfileCatalog()
    source = MemorySource(None)
    runtime = UsersRuntime()
    resolver = UsersAccessResolver(source=source, runtime=runtime, profiles=profiles)

    with server.test_request_context('/'):
        identity = _identity()
        decision = resolver.resolve(identity, load_id='load-1')
        access = AccessSnapshot.resolved(
            load_id='load-1',
            identity=identity,
            decision=AccessDecision(status=AccessStatus.READY, user_id=decision.user_id),
        )
        user = runtime.current(access)

    assert decision.status is AccessStatus.READY
    assert decision.user_id is not None
    assert decision.user_id.startswith('pending:')
    assert user.pending is True
    assert user.profile.key == 'guest'
    assert source.calls == 1


def test_disabled_user_returns_disabled_access_decision() -> None:
    from flask import Flask

    server = Flask(__name__)
    server.secret_key = 'test-only'
    profiles = ProfileCatalog()
    source = MemorySource(
        ResolvedUserRecord(
            user_id='user-1',
            subject_id='oid-1',
            display_name='Disabled User',
            email='disabled@example.com',
            enabled=False,
            profile_key='administrator',
        )
    )
    resolver = UsersAccessResolver(source=source, runtime=UsersRuntime(), profiles=profiles)

    with server.test_request_context('/'):
        decision = resolver.resolve(_identity(), load_id='load-1')

    assert decision.status is AccessStatus.USER_DISABLED
    assert decision.user_id == 'user-1'


def test_identity_conflict_is_reported_as_users_service_unavailable() -> None:
    from flask import Flask

    from atlanticus.web.identity.errors import AccessResolverUnavailableError
    from atlanticus.web.users.errors import UsersIdentityConflictError

    class ConflictSource(UsersSource):
        def resolve(self, identity: AuthenticatedIdentity) -> ResolvedUserRecord | None:
            del identity
            raise UsersIdentityConflictError('conflict')

    server = Flask(__name__)
    server.secret_key = 'test-only'
    resolver = UsersAccessResolver(
        source=ConflictSource(),
        runtime=UsersRuntime(),
        profiles=ProfileCatalog(),
    )

    with server.test_request_context('/'):
        with pytest.raises(AccessResolverUnavailableError, match='Users source is unavailable'):
            resolver.resolve(_identity(), load_id='load-1')
