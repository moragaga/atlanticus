# Orquesta Activity sin conocer Flask, Cosmos ni JavaScript.
# Acumula tiempo sólo desde un estado previamente visible y limita deltas anómalos.
# Los conflictos optimistas se reintentan; secuencias ya aplicadas son idempotentes.
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from atlanticus.web.identity.access import AccessSnapshot, AccessStatus
from atlanticus.web.users.activity.contracts import ActivityRouteResolver, UserActivityRepository
from atlanticus.web.users.activity.errors import UserActivityConflictError, UserActivityError
from atlanticus.web.users.activity.models import (
    RouteActivity,
    UserActivityDocument,
    UserActivityEvent,
    UserActivityEventType,
    activity_document_id,
    actor_key,
)


class UserActivityService:
    def __init__(
        self,
        *,
        repository: UserActivityRepository,
        application_key: str,
        route_resolver: ActivityRouteResolver | None = None,
        track_local: bool = False,
        max_active_delta_seconds: int = 600,
        max_routes: int = 64,
        max_conflict_retries: int = 3,
    ) -> None:
        application_key = application_key.strip()
        if not application_key:
            raise UserActivityError('Application key must not be empty')
        if max_active_delta_seconds < 1:
            raise UserActivityError('Maximum active delta must be positive')
        if max_routes < 1:
            raise UserActivityError('Maximum route count must be positive')
        if max_conflict_retries < 1:
            raise UserActivityError('Maximum conflict retries must be positive')
        self._repository = repository
        self._application_key = application_key
        self._route_resolver = route_resolver
        self._track_local = track_local
        self._max_active_delta_seconds = max_active_delta_seconds
        self._max_routes = max_routes
        self._max_conflict_retries = max_conflict_retries

    def should_track(self, snapshot: AccessSnapshot | None) -> bool:
        if (
            snapshot is None
            or snapshot.status is not AccessStatus.READY
            or snapshot.identity is None
        ):
            return False
        return self._track_local or snapshot.identity.provider_key != 'local'

    def capture(
        self,
        *,
        snapshot: AccessSnapshot,
        event: UserActivityEvent,
        now: datetime | None = None,
    ) -> dict[str, object]:
        if not self.should_track(snapshot):
            return {'tracked': False, 'status': 'skipped'}
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        identity = snapshot.identity
        if identity is None:
            return {'tracked': False, 'status': 'skipped'}
        actor = actor_key(snapshot)
        document_id = activity_document_id(
            application_key=self._application_key,
            actor=actor,
            client_session_id=event.client_session_id,
        )
        for _ in range(self._max_conflict_retries):
            stored = self._repository.load(document_id=document_id, partition_key=actor)
            if stored is None:
                document = self._create_document(
                    snapshot=snapshot,
                    event=event,
                    actor=actor,
                    observed_at=observed_at,
                )
                expected_revision = None
            else:
                if event.sequence <= stored.document.last_sequence:
                    return {'tracked': True, 'status': 'duplicate', 'document_id': document_id}
                document = self._apply_event(stored.document, event=event, observed_at=observed_at)
                expected_revision = stored.revision
            try:
                saved = self._repository.save(document, expected_revision=expected_revision)
            except UserActivityConflictError:
                continue
            return {
                'tracked': True,
                'status': 'captured',
                'document_id': saved.document.id,
                'revision': saved.revision,
            }
        raise UserActivityError('User activity event could not be persisted after conflicts')

    def _create_document(
        self,
        *,
        snapshot: AccessSnapshot,
        event: UserActivityEvent,
        actor: str,
        observed_at: datetime,
    ) -> UserActivityDocument:
        identity = snapshot.identity
        if identity is None:
            raise UserActivityError('Ready access snapshot is required for user activity')
        route_key = self._resolve_route_key(event.pathname)
        visible = _event_is_visible(event)
        route = RouteActivity(pathname=event.pathname, views=1 if visible else 0)
        return UserActivityDocument(
            id=activity_document_id(
                application_key=self._application_key,
                actor=actor,
                client_session_id=event.client_session_id,
            ),
            partition_key=actor,
            application_key=self._application_key,
            actor_key=actor,
            provider_key=identity.provider_key,
            user_id=snapshot.user_id,
            client_session_id=event.client_session_id,
            first_seen_at_utc=observed_at,
            last_seen_at_utc=observed_at,
            active_seconds=0,
            page_views=1 if visible else 0,
            visibility_resumes=0,
            visibility_state='visible' if visible else 'hidden',
            current_pathname=event.pathname,
            current_route_key=route_key,
            initial_viewport=event.viewport,
            last_viewport=event.viewport,
            initial_screen=event.screen,
            last_screen=event.screen,
            routes={route_key: route},
            last_sequence=event.sequence,
            last_event_id=event.event_id,
        )

    def _apply_event(
        self,
        current: UserActivityDocument,
        *,
        event: UserActivityEvent,
        observed_at: datetime,
    ) -> UserActivityDocument:
        elapsed = max(0, int((observed_at - current.last_seen_at_utc).total_seconds()))
        elapsed = min(elapsed, self._max_active_delta_seconds)
        routes = dict(current.routes)
        active_seconds = current.active_seconds
        if current.visibility_state == 'visible' and elapsed:
            active_seconds += elapsed
            route = routes.get(current.current_route_key)
            if route is not None:
                routes[current.current_route_key] = route.add_time(elapsed)

        route_key = self._resolve_route_key(event.pathname)
        pathname_changed = event.pathname != current.current_pathname
        visible_now = _event_is_visible(event)
        page_views = current.page_views
        if pathname_changed and visible_now:
            page_views += 1
            route = routes.get(route_key)
            if route is None and len(routes) < self._max_routes:
                routes[route_key] = RouteActivity(pathname=event.pathname, views=1)
            elif route is not None:
                routes[route_key] = route.add_view(event.pathname)

        resumes = current.visibility_resumes
        if (
            current.visibility_state == 'hidden'
            and event.event_type is UserActivityEventType.VISIBLE
        ):
            resumes += 1

        return replace(
            current,
            last_seen_at_utc=observed_at,
            active_seconds=active_seconds,
            page_views=page_views,
            visibility_resumes=resumes,
            visibility_state='visible' if visible_now else 'hidden',
            current_pathname=event.pathname,
            current_route_key=route_key,
            last_viewport=event.viewport,
            last_screen=event.screen,
            routes=routes,
            last_sequence=event.sequence,
            last_event_id=event.event_id,
        )

    def _resolve_route_key(self, pathname: str) -> str:
        if self._route_resolver is not None:
            route = self._route_resolver.resolve(pathname)
            if route is not None:
                return route.key
        return f'path:{pathname}'


def _event_is_visible(event: UserActivityEvent) -> bool:
    if event.event_type in {UserActivityEventType.HIDDEN, UserActivityEventType.PAGEHIDE}:
        return False
    if event.event_type is UserActivityEventType.VISIBLE:
        return True
    return event.visibility_state == 'visible'
