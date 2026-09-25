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
from atlanticus.web.users.models import EffectiveUser
from atlanticus.web.users.runtime import UsersRuntime


def _snapshot(state: dict[str, object]) -> AccessSnapshot:
    return AccessSnapshot(
        load_id=str(state['load_id']),
        resolved_at_utc=datetime(2026, 8, 31, tzinfo=UTC).isoformat(),
        status=state['status'],
        identity=AuthenticatedIdentity(
            provider_key=str(state['provider_key']),
            issuer='issuer',
            subject_id=str(state['subject_id']),
        ),
        user_id=str(state['user_id']),
    )


def _user(state: dict[str, object]) -> EffectiveUser:
    is_local = state['provider_key'] == 'local' and not state['managed_local']
    return EffectiveUser(
        user_id=str(state['user_id']),
        subject_id=str(state['subject_id']),
        display_name='Tester',
        email=None,
        enabled=bool(state['enabled']),
        avatar_text='TE',
        profile_key='local' if is_local else 'basic',
        is_local=is_local,
    )


def _app(*, promoted: bool = True, provider_key: str = 'entra', track_local: bool = False):
    app = Flask(__name__)
    app.secret_key = 'test-only'
    services = ServiceRegistry()
    identity_runtime = AccessRuntime()
    activity_runtime = AccessRuntime()
    users_runtime = UsersRuntime()
    repository = MemoryUserActivityRepository()
    state = {
        'promoted': promoted,
        'provider_key': provider_key,
        'status': AccessStatus.READY,
        'load_id': 'load-1',
        'subject_id': 'subject',
        'user_id': 'user-1',
        'enabled': True,
        'managed_local': False,
    }
    services.add(ACCESS_RUNTIME_SERVICE_KEY, activity_runtime)
    services.add(
        USER_ACTIVITY_SERVICE_KEY,
        UserActivityService(
            repository=repository,
            application_key='app',
            users_runtime=users_runtime,
            track_local=track_local,
        ),
    )

    @app.before_request
    def bind_access():
        snapshot = _snapshot(state)
        identity_runtime.store(snapshot)
        if state['promoted']:
            users_runtime.store(load_id=snapshot.load_id, user=_user(state))

    register_user_activity_routes(app, services)
    return app, repository, state


def _event() -> dict[str, object]:
    return {
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
    }


def test_unpromoted_identity_is_not_eligible_even_with_deterministic_user_id() -> None:
    app, repository, _ = _app(promoted=False)
    client = app.test_client()

    bootstrap = client.get('/_atlanticus/activity/bootstrap')
    assert bootstrap.status_code == 200
    assert bootstrap.get_json() == {'enabled': True, 'track': False}
    direct = client.post('/_atlanticus/activity/events', json=_event())
    assert direct.status_code == 403
    assert repository.documents() == ()


def test_promoted_identity_is_eligible_across_two_access_runtime_instances() -> None:
    app, repository, _ = _app()
    client = app.test_client()

    bootstrap = client.get('/_atlanticus/activity/bootstrap')
    assert bootstrap.status_code == 200
    assert bootstrap.get_json() == {'enabled': True, 'track': True}
    direct = client.post('/_atlanticus/activity/events', json=_event())
    assert direct.status_code == 202
    assert direct.get_json()['status'] == 'captured'
    assert len(repository.documents()) == 1
    assert repository.documents()[0].user_id == 'user-1'


def test_disabled_identity_does_not_capture_events() -> None:
    app, repository, state = _app()
    state['status'] = AccessStatus.USER_DISABLED
    state['enabled'] = False
    client = app.test_client()

    assert client.get('/_atlanticus/activity/bootstrap').get_json()['track'] is False
    assert client.post('/_atlanticus/activity/events', json=_event()).status_code == 403
    assert repository.documents() == ()


def test_switching_identity_cannot_reuse_previous_user_snapshot() -> None:
    app, repository, state = _app()
    client = app.test_client()
    assert client.get('/_atlanticus/activity/bootstrap').get_json()['track'] is True

    state['load_id'] = 'load-2'
    state['subject_id'] = 'other-subject'
    state['user_id'] = 'other-user'
    state['promoted'] = False

    assert client.get('/_atlanticus/activity/bootstrap').get_json()['track'] is False
    assert client.post('/_atlanticus/activity/events', json=_event()).status_code == 403
    assert repository.documents() == ()


def test_identity_mismatch_is_denied_even_if_load_id_is_reused() -> None:
    app, repository, state = _app()
    client = app.test_client()
    assert client.get('/_atlanticus/activity/bootstrap').get_json()['track'] is True

    state['subject_id'] = 'another-subject'
    state['promoted'] = False

    assert client.get('/_atlanticus/activity/bootstrap').get_json()['track'] is False
    assert client.post('/_atlanticus/activity/events', json=_event()).status_code == 403
    assert repository.documents() == ()


def test_local_tracking_requires_opt_in_and_promotion() -> None:
    app, repository, _ = _app(provider_key='local')
    client = app.test_client()
    assert client.get('/_atlanticus/activity/bootstrap').get_json()['track'] is False
    assert client.post('/_atlanticus/activity/events', json=_event()).status_code == 403
    assert repository.documents() == ()

    opted_in, opted_repo, _ = _app(provider_key='local', track_local=True)
    opted_client = opted_in.test_client()
    assert opted_client.get('/_atlanticus/activity/bootstrap').get_json()['track'] is False
    assert opted_client.post('/_atlanticus/activity/events', json=_event()).status_code == 403
    assert opted_repo.documents() == ()

    unpromoted, unpromoted_repo, _ = _app(promoted=False, provider_key='local', track_local=True)
    unpromoted_client = unpromoted.test_client()
    assert unpromoted_client.get('/_atlanticus/activity/bootstrap').get_json()['track'] is False
    assert unpromoted_client.post('/_atlanticus/activity/events', json=_event()).status_code == 403
    assert unpromoted_repo.documents() == ()

    managed, managed_repo, managed_state = _app(provider_key='local', track_local=True)
    managed_state['managed_local'] = True
    managed_client = managed.test_client()
    assert managed_client.get('/_atlanticus/activity/bootstrap').get_json()['track'] is True
    assert managed_client.post('/_atlanticus/activity/events', json=_event()).status_code == 202
    assert len(managed_repo.documents()) == 1


def test_event_route_rejects_invalid_payload_for_promoted_user() -> None:
    app, _, _ = _app()
    response = app.test_client().post('/_atlanticus/activity/events', json={'sequence': 0})
    assert response.status_code == 400
    assert response.get_json()['error']
