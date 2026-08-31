from datetime import UTC, datetime

from flask import Flask

from atlanticus.web.identity.access import (
    ACCESS_RUNTIME_SERVICE_KEY,
    AccessRuntime,
    AccessSnapshot,
    AccessStatus,
)
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.users.activity.adapters.memory import MemoryUserActivityRepository
from atlanticus.web.users.activity.routes import (
    USER_ACTIVITY_SERVICE_KEY,
    register_user_activity_routes,
)
from atlanticus.web.users.activity.services import UserActivityService


def _snapshot(provider_key: str = 'entra') -> AccessSnapshot:
    return AccessSnapshot(
        load_id='load',
        resolved_at_utc=datetime(2026, 8, 31, tzinfo=UTC).isoformat(),
        status=AccessStatus.READY,
        identity=AuthenticatedIdentity(
            provider_key=provider_key,
            issuer='issuer',
            subject_id='subject',
        ),
        user_id='user-1',
    )


def _app(provider_key: str = 'entra'):
    app = Flask(__name__)
    app.secret_key = 'test-only'
    services = ServiceRegistry()
    access = AccessRuntime()
    repository = MemoryUserActivityRepository()
    services.add(ACCESS_RUNTIME_SERVICE_KEY, access)
    services.add(
        USER_ACTIVITY_SERVICE_KEY,
        UserActivityService(repository=repository, application_key='app'),
    )

    @app.before_request
    def bind_access():
        access.store(_snapshot(provider_key))

    register_user_activity_routes(app, services)
    return app, repository


def test_bootstrap_respects_local_tracking_policy() -> None:
    app, _ = _app('local')

    response = app.test_client().get('/_atlanticus/activity/bootstrap')

    assert response.status_code == 200
    assert response.get_json() == {'enabled': True, 'track': False}


def test_event_route_accepts_valid_event() -> None:
    app, repository = _app()

    response = app.test_client().post(
        '/_atlanticus/activity/events',
        json={
            'event_id': 'event-1',
            'client_session_id': 'session-1',
            'sequence': 1,
            'event_type': 'register',
            'pathname': '/',
            'previous_pathname': None,
            'visibility_state': 'visible',
            'viewport': {'width': 100, 'height': 100},
            'screen': {'width': 100, 'height': 100, 'pixel_ratio': 1},
            'client_timestamp_utc': '2026-08-31T12:00:00+00:00',
        },
    )

    assert response.status_code == 202
    assert response.get_json()['status'] == 'captured'
    assert len(repository.documents()) == 1


def test_event_route_rejects_invalid_payload() -> None:
    app, _ = _app()

    response = app.test_client().post('/_atlanticus/activity/events', json={'sequence': 0})

    assert response.status_code == 400
    assert response.get_json()['error']
