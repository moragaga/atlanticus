from datetime import UTC, datetime, timedelta

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


class _Routes:
    def resolve(self, pathname: str) -> ActivityRoute | None:
        routes = {'/': 'home', '/manager': 'manager'}
        key = routes.get(pathname)
        return ActivityRoute(key=key, pathname=pathname) if key else None


def _snapshot(*, provider_key: str = 'entra', user_id: str | None = 'user-1') -> AccessSnapshot:
    return AccessSnapshot(
        load_id='load-1',
        resolved_at_utc=datetime(2026, 8, 31, tzinfo=UTC).isoformat(),
        status=AccessStatus.READY,
        identity=AuthenticatedIdentity(
            provider_key=provider_key,
            issuer='issuer',
            subject_id='subject-1',
            display_name='Should not be persisted',
            email='should-not-be-persisted@example.com',
        ),
        user_id=user_id,
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


def test_local_identity_is_not_tracked_by_default() -> None:
    repository = MemoryUserActivityRepository()
    service = UserActivityService(repository=repository, application_key='app')

    result = service.capture(
        snapshot=_snapshot(provider_key='local'),
        event=_event(1, UserActivityEventType.REGISTER),
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )

    assert result == {'tracked': False, 'status': 'skipped'}
    assert repository.documents() == ()


def test_activity_accumulates_only_visible_time_and_tracks_routes() -> None:
    repository = MemoryUserActivityRepository()
    service = UserActivityService(
        repository=repository,
        application_key='app',
        route_resolver=_Routes(),
    )
    start = datetime(2026, 8, 31, tzinfo=UTC)
    snapshot = _snapshot()

    service.capture(snapshot=snapshot, event=_event(1, UserActivityEventType.REGISTER), now=start)
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


def test_duplicate_sequence_is_idempotent() -> None:
    repository = MemoryUserActivityRepository()
    service = UserActivityService(repository=repository, application_key='app')
    start = datetime(2026, 8, 31, tzinfo=UTC)
    snapshot = _snapshot(user_id=None)

    service.capture(snapshot=snapshot, event=_event(1, UserActivityEventType.REGISTER), now=start)
    result = service.capture(
        snapshot=snapshot,
        event=_event(1, UserActivityEventType.HEARTBEAT),
        now=start + timedelta(seconds=30),
    )

    assert result['status'] == 'duplicate'
    document = repository.documents()[0]
    assert document.active_seconds == 0
    assert document.actor_key.startswith('identity:')


def test_activity_document_excludes_display_name_and_email() -> None:
    repository = MemoryUserActivityRepository()
    service = UserActivityService(repository=repository, application_key='app')

    service.capture(
        snapshot=_snapshot(),
        event=_event(1, UserActivityEventType.REGISTER),
        now=datetime(2026, 8, 31, tzinfo=UTC),
    )

    payload = repository.documents()[0].to_document()
    assert 'display_name' not in payload
    assert 'email' not in payload
    assert 'subject_id' not in payload
