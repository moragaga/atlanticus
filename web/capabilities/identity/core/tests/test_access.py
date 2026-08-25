import pytest
from flask import Flask

from atlanticus.web.identity.access import (
    AccessDecision,
    AccessRuntime,
    AccessSnapshot,
    AccessStatus,
)
from atlanticus.web.identity.errors import AccessContextError, IdentityDefinitionError
from atlanticus.web.identity.models import AuthenticatedIdentity


def _identity() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(
        provider_key='local',
        issuer='local',
        subject_id='subject',
        display_name='John Doe',
        email='john.doe@example.com',
    )


def test_access_snapshot_round_trips_through_flask_session() -> None:
    server = Flask(__name__)
    server.secret_key = 'test-only'
    runtime = AccessRuntime()
    snapshot = AccessSnapshot.resolved(
        load_id='load-1',
        identity=_identity(),
        decision=AccessDecision(status=AccessStatus.READY, user_id='user-1'),
    )

    with server.test_request_context('/'):
        runtime.store(snapshot)
        restored = runtime.current()

    assert restored.load_id == snapshot.load_id
    assert restored.identity is not None
    assert restored.identity.subject_id == snapshot.identity.subject_id
    assert restored.identity.display_name is None
    assert restored.identity.email is None
    assert restored.user_id == 'user-1'


def test_access_runtime_requires_snapshot() -> None:
    server = Flask(__name__)
    server.secret_key = 'test-only'
    with server.test_request_context('/'):
        with pytest.raises(AccessContextError, match='not available'):
            AccessRuntime().current()


def test_disabled_decision_requires_user_id() -> None:
    with pytest.raises(IdentityDefinitionError, match='requires user_id'):
        AccessDecision(status=AccessStatus.USER_DISABLED)


def test_access_runtime_rejects_usage_outside_request() -> None:
    with pytest.raises(AccessContextError, match='inside a request'):
        AccessRuntime().current_or_none()
