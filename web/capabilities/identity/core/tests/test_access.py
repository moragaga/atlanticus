import pytest
from flask import Flask, session

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
    assert restored.bootstrap_root is False


def test_bootstrap_root_snapshot_round_trips_through_flask_session() -> None:
    server = Flask(__name__)
    server.secret_key = 'test-only'
    runtime = AccessRuntime()
    snapshot = AccessSnapshot.resolved(
        load_id='load-root',
        identity=_identity(),
        decision=AccessDecision(status=AccessStatus.READY, bootstrap_root=True),
    )

    with server.test_request_context('/'):
        runtime.store(snapshot)
        restored = runtime.current()

    assert restored.status is AccessStatus.READY
    assert restored.user_id is None
    assert restored.bootstrap_root is True


def test_access_runtime_ignores_previous_snapshot_contract() -> None:
    server = Flask(__name__)
    server.secret_key = 'test-only'
    with server.test_request_context('/'):
        session['_atlanticus_access_snapshot'] = {'status': 'ready'}
        assert AccessRuntime().current_or_none() is None


def test_access_runtime_requires_snapshot() -> None:
    server = Flask(__name__)
    server.secret_key = 'test-only'
    with server.test_request_context('/'):
        with pytest.raises(AccessContextError, match='not available'):
            AccessRuntime().current()


def test_disabled_decision_requires_user_id() -> None:
    with pytest.raises(IdentityDefinitionError, match='requires user_id'):
        AccessDecision(status=AccessStatus.USER_DISABLED)


def test_bootstrap_root_decision_requires_ready_status() -> None:
    with pytest.raises(IdentityDefinitionError, match='must be ready'):
        AccessDecision(
            status=AccessStatus.USER_DISABLED,
            user_id='user-1',
            bootstrap_root=True,
        )


def test_bootstrap_root_decision_rejects_user_id() -> None:
    with pytest.raises(IdentityDefinitionError, match='cannot contain user_id'):
        AccessDecision(
            status=AccessStatus.READY,
            user_id='user-1',
            bootstrap_root=True,
        )


def test_bootstrap_root_snapshot_rejects_user_id() -> None:
    with pytest.raises(IdentityDefinitionError, match='cannot contain user_id'):
        AccessSnapshot(
            load_id='load-root',
            resolved_at_utc='2026-09-14T12:00:00+00:00',
            status=AccessStatus.READY,
            identity=_identity(),
            user_id='user-1',
            bootstrap_root=True,
        )


def test_access_snapshot_session_requires_bootstrap_root_flag() -> None:
    value = AccessSnapshot.resolved(
        load_id='load-1',
        identity=_identity(),
        decision=AccessDecision(status=AccessStatus.READY),
    ).to_session()
    value.pop('bootstrap_root')

    with pytest.raises(AccessContextError, match='invalid'):
        AccessSnapshot.from_session(value)


def test_access_runtime_rejects_usage_outside_request() -> None:
    with pytest.raises(AccessContextError, match='inside a request'):
        AccessRuntime().current_or_none()
