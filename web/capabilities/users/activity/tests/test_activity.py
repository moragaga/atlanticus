from datetime import UTC, datetime, timedelta

from flask import Flask

from atlanticus.web.identity.access import AccessSnapshot, AccessStatus
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.activity import (
    ActivityRoute,
    MemoryUserActivityRepository,
    Screen,
    UserActivityEvent,
    UserActivityEventType,
    UserActivityService,
    Viewport,
)
from atlanticus.web.users.models import EffectiveUser
from atlanticus.web.users.runtime import UsersRuntime


class _Routes:
    def resolve(self, pathname: str) -> ActivityRoute | None:
        routes = {'/': 'home', '/manager': 'manager'}
        key = routes.get(pathname)
        return ActivityRoute(key=key, pathname=pathname) if key else None


def _snapshot(
    *,
    provider_key: str = 'entra',
    user_id: str | None = 'user-1',
    subject_id: str = 'subject-1',
    load_id: str = 'load-1',
    status: AccessStatus = AccessStatus.READY,
    bootstrap_root: bool = False,
) -> AccessSnapshot:
    return AccessSnapshot(
        load_id=load_id,
        resolved_at_utc=datetime(2026, 8, 31, tzinfo=UTC).isoformat(),
        status=status,
        identity=AuthenticatedIdentity(
            provider_key=provider_key,
            issuer='issuer',
            subject_id=subject_id,
            display_name='Should not be persisted',
            email='should-not-be-persisted@example.com',
        ),
        user_id=user_id,
        bootstrap_root=bootstrap_root,
    )


def _user(
    *,
    user_id: str = 'user-1',
    subject_id: str = 'subject-1',
    enabled: bool = True,
    local: bool = False,
) -> EffectiveUser:
    return EffectiveUser(
        user_id=user_id,
        subject_id=subject_id,
        display_name='Tester',
        email=None,
        enabled=enabled,
        avatar_text='TE',
        profile_key='local' if local else 'basic',
        is_local=local,
    )


def _event(
    sequence: int,
    event_type: UserActivityEventType,
    *,
    pathname: str = '/',
    visibility: str = 'visible',
) -> UserActivityEvent:
    return UserActivityEvent(
        event_id=f'event-{sequence}',
        client_session_id='session-1',
        sequence=sequence,
        event_type=event_type,
        pathname=pathname,
        previous_pathname=None,
        visibility_state=visibility,
        viewport=Viewport(1280, 720),
        screen=Screen(1920, 1080, 2.0),
    )


def _service(*, users: UsersRuntime, repository: MemoryUserActivityRepository, **settings):
    return UserActivityService(
        repository=repository,
        application_key='app',
        users_runtime=users,
        **settings,
    )


def test_no_promoted_user_does_not_capture_activity() -> None:
    app = Flask(__name__)
    app.secret_key = 'test-only'
    repository = MemoryUserActivityRepository()
    service = _service(users=UsersRuntime(), repository=repository)

    with app.test_request_context('/'):
        snapshot = _snapshot()
        assert snapshot.user_id is not None
        assert service.should_track(snapshot) is False
        assert service.capture(
            snapshot=snapshot, event=_event(1, UserActivityEventType.REGISTER)
        ) == {
            'tracked': False,
            'status': 'skipped',
        }
        assert repository.documents() == ()


def test_local_identity_is_not_tracked_by_default_even_when_promoted() -> None:
    app = Flask(__name__)
    app.secret_key = 'test-only'
    users = UsersRuntime()
    repository = MemoryUserActivityRepository()
    service = _service(users=users, repository=repository)

    with app.test_request_context('/'):
        snapshot = _snapshot(provider_key='local')
        users.store(load_id=snapshot.load_id, user=_user(local=True))
        result = service.capture(
            snapshot=snapshot,
            event=_event(1, UserActivityEventType.REGISTER),
            now=datetime(2026, 8, 31, tzinfo=UTC),
        )
        assert result == {'tracked': False, 'status': 'skipped'}
        assert repository.documents() == ()


def test_local_tracking_opt_in_rejects_bootstrap_user_until_managed() -> None:
    app = Flask(__name__)
    app.secret_key = 'test-only'
    users = UsersRuntime()
    repository = MemoryUserActivityRepository()
    service = _service(users=users, repository=repository, track_local=True)

    with app.test_request_context('/'):
        snapshot = _snapshot(provider_key='local')
        assert service.should_track(snapshot) is False
        users.store(load_id=snapshot.load_id, user=_user(local=True))
        assert service.should_track(snapshot) is False
        users.store(load_id=snapshot.load_id, user=_user(local=False))
        assert service.should_track(snapshot) is True


def test_activity_accumulates_only_visible_time_and_tracks_routes() -> None:
    app = Flask(__name__)
    app.secret_key = 'test-only'
    users = UsersRuntime()
    repository = MemoryUserActivityRepository()
    service = _service(users=users, repository=repository, route_resolver=_Routes())
    start = datetime(2026, 8, 31, tzinfo=UTC)
    snapshot = _snapshot()

    with app.test_request_context('/'):
        users.store(load_id=snapshot.load_id, user=_user())
        service.capture(
            snapshot=snapshot,
            event=_event(1, UserActivityEventType.REGISTER),
            now=start,
        )
        service.capture(
            snapshot=snapshot,
            event=_event(2, UserActivityEventType.HEARTBEAT),
            now=start + timedelta(seconds=30),
        )
        service.capture(
            snapshot=snapshot,
            event=_event(3, UserActivityEventType.HIDDEN, visibility='hidden'),
            now=start + timedelta(seconds=40),
        )
        service.capture(
            snapshot=snapshot,
            event=_event(4, UserActivityEventType.VISIBLE),
            now=start + timedelta(seconds=100),
        )
        service.capture(
            snapshot=snapshot,
            event=_event(5, UserActivityEventType.ROUTE_CHANGED, pathname='/manager'),
            now=start + timedelta(seconds=110),
        )
        service.capture(
            snapshot=snapshot,
            event=_event(6, UserActivityEventType.HEARTBEAT, pathname='/manager'),
            now=start + timedelta(seconds=130),
        )

    document = repository.documents()[0]
    assert document.active_seconds == 70
    assert document.page_views == 2
    assert document.visibility_resumes == 1
    assert document.current_route_key == 'manager'
    assert document.routes['home'].active_seconds == 50
    assert document.routes['manager'].active_seconds == 20
    assert document.routes['manager'].views == 1


def test_duplicate_sequence_is_idempotent_for_promoted_user() -> None:
    app = Flask(__name__)
    app.secret_key = 'test-only'
    users = UsersRuntime()
    repository = MemoryUserActivityRepository()
    service = _service(users=users, repository=repository)
    start = datetime(2026, 8, 31, tzinfo=UTC)
    snapshot = _snapshot()

    with app.test_request_context('/'):
        users.store(load_id=snapshot.load_id, user=_user())
        service.capture(
            snapshot=snapshot,
            event=_event(1, UserActivityEventType.REGISTER),
            now=start,
        )
        result = service.capture(
            snapshot=snapshot,
            event=_event(1, UserActivityEventType.HEARTBEAT),
            now=start + timedelta(seconds=30),
        )

    assert result['status'] == 'duplicate'
    document = repository.documents()[0]
    assert document.active_seconds == 0
    assert document.actor_key.startswith('user:')


def test_disabled_and_stale_users_are_denied_before_repository_access() -> None:
    app = Flask(__name__)
    app.secret_key = 'test-only'
    users = UsersRuntime()
    repository = MemoryUserActivityRepository()
    service = _service(users=users, repository=repository)

    with app.test_request_context('/'):
        current = _snapshot()
        users.store(load_id=current.load_id, user=_user(enabled=False))
        assert service.should_track(current) is False
        assert service.should_track(_snapshot(load_id='new-load')) is False
        assert service.should_track(_snapshot(subject_id='different-subject')) is False
        assert service.should_track(_snapshot(user_id='different-user')) is False
        assert service.should_track(
            _snapshot(status=AccessStatus.USER_DISABLED)
        ) is False
        assert repository.documents() == ()


def test_bootstrap_root_cannot_enable_tracking() -> None:
    app = Flask(__name__)
    app.secret_key = 'test-only'
    users = UsersRuntime()
    repository = MemoryUserActivityRepository()
    service = _service(users=users, repository=repository, track_local=True)

    with app.test_request_context('/'):
        snapshot = _snapshot(provider_key='local', user_id=None, bootstrap_root=True)
        assert service.should_track(snapshot) is False
        assert repository.documents() == ()


def test_activity_document_excludes_display_name_and_email() -> None:
    app = Flask(__name__)
    app.secret_key = 'test-only'
    users = UsersRuntime()
    repository = MemoryUserActivityRepository()
    service = _service(users=users, repository=repository)

    with app.test_request_context('/'):
        snapshot = _snapshot()
        users.store(load_id=snapshot.load_id, user=_user())
        service.capture(
            snapshot=snapshot,
            event=_event(1, UserActivityEventType.REGISTER),
            now=datetime(2026, 8, 31, tzinfo=UTC),
        )

    payload = repository.documents()[0].to_document()
    assert 'display_name' not in payload
    assert 'email' not in payload
    assert 'subject_id' not in payload
