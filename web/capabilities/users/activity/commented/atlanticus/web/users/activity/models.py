# Modela eventos del browser y el agregado funcional de sesión.
# No persiste nombre, email ni subject_id crudo; usa una identidad funcional mínima.
# El servidor deriva active_seconds y no confía en un contador enviado por el browser.
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import urlsplit

from atlanticus.web.identity.access import AccessSnapshot, AccessStatus
from atlanticus.web.users.activity.errors import UserActivityError

USER_ACTIVITY_DOCUMENT_TYPE = 'user_activity_session'
USER_ACTIVITY_SCHEMA_VERSION = 1
USER_ACTIVITY_PARTITION_KEY_PATH = '/partition_key'


class UserActivityEventType(StrEnum):
    REGISTER = 'register'
    HEARTBEAT = 'heartbeat'
    HIDDEN = 'hidden'
    VISIBLE = 'visible'
    ROUTE_CHANGED = 'route_changed'
    PAGEHIDE = 'pagehide'


@dataclass(frozen=True, slots=True)
class Viewport:
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width < 0 or self.height < 0:
            raise UserActivityError('Viewport dimensions must not be negative')

    @classmethod
    def from_value(cls, value: object) -> Viewport:
        payload = value if isinstance(value, Mapping) else {}
        return cls(width=_dimension(payload.get('width')), height=_dimension(payload.get('height')))

    def to_document(self) -> dict[str, int]:
        return {'width': self.width, 'height': self.height}


@dataclass(frozen=True, slots=True)
class Screen:
    width: int
    height: int
    pixel_ratio: float

    def __post_init__(self) -> None:
        if self.width < 0 or self.height < 0:
            raise UserActivityError('Screen dimensions must not be negative')
        if self.pixel_ratio <= 0:
            raise UserActivityError('Screen pixel ratio must be positive')

    @classmethod
    def from_value(cls, value: object) -> Screen:
        payload = value if isinstance(value, Mapping) else {}
        return cls(
            width=_dimension(payload.get('width')),
            height=_dimension(payload.get('height')),
            pixel_ratio=_ratio(payload.get('pixel_ratio')),
        )

    def to_document(self) -> dict[str, int | float]:
        return {'width': self.width, 'height': self.height, 'pixel_ratio': self.pixel_ratio}


@dataclass(frozen=True, slots=True)
class UserActivityEvent:
    event_id: str
    client_session_id: str
    sequence: int
    event_type: UserActivityEventType
    pathname: str
    previous_pathname: str | None
    visibility_state: str
    viewport: Viewport
    screen: Screen
    client_timestamp_utc: datetime | None = None

    def __post_init__(self) -> None:
        event_id = self.event_id.strip()
        client_session_id = self.client_session_id.strip()
        if not event_id:
            raise UserActivityError('User activity event id must not be empty')
        if not client_session_id:
            raise UserActivityError('User activity client session id must not be empty')
        if self.sequence < 1:
            raise UserActivityError('User activity sequence must be positive')
        if self.visibility_state not in {'visible', 'hidden'}:
            raise UserActivityError('User activity visibility state is invalid')
        object.__setattr__(self, 'event_id', event_id[:120])
        object.__setattr__(self, 'client_session_id', client_session_id[:120])
        object.__setattr__(self, 'pathname', normalize_pathname(self.pathname))
        if self.previous_pathname is not None:
            object.__setattr__(
                self, 'previous_pathname', normalize_pathname(self.previous_pathname)
            )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> UserActivityEvent:
        try:
            event_type = UserActivityEventType(str(payload.get('event_type') or ''))
            sequence = int(payload.get('sequence'))
        except (TypeError, ValueError) as error:
            raise UserActivityError('User activity payload is invalid') from error
        previous = payload.get('previous_pathname')
        return cls(
            event_id=str(payload.get('event_id') or ''),
            client_session_id=str(payload.get('client_session_id') or ''),
            sequence=sequence,
            event_type=event_type,
            pathname=str(payload.get('pathname') or '/'),
            previous_pathname=str(previous) if previous else None,
            visibility_state=str(payload.get('visibility_state') or 'visible'),
            viewport=Viewport.from_value(payload.get('viewport')),
            screen=Screen.from_value(payload.get('screen')),
            client_timestamp_utc=_optional_datetime(payload.get('client_timestamp_utc')),
        )


@dataclass(frozen=True, slots=True)
class RouteActivity:
    pathname: str
    views: int = 0
    active_seconds: int = 0

    def __post_init__(self) -> None:
        if self.views < 0 or self.active_seconds < 0:
            raise UserActivityError('Route activity values must not be negative')
        object.__setattr__(self, 'pathname', normalize_pathname(self.pathname))

    def add_time(self, seconds: int) -> RouteActivity:
        return replace(self, active_seconds=self.active_seconds + max(0, seconds))

    def add_view(self, pathname: str) -> RouteActivity:
        return replace(self, pathname=normalize_pathname(pathname), views=self.views + 1)

    def to_document(self) -> dict[str, int | str]:
        return {
            'pathname': self.pathname,
            'views': self.views,
            'active_seconds': self.active_seconds,
        }

    @classmethod
    def from_value(cls, value: object) -> RouteActivity:
        payload = value if isinstance(value, Mapping) else {}
        return cls(
            pathname=str(payload.get('pathname') or '/'),
            views=_non_negative_int(payload.get('views')),
            active_seconds=_non_negative_int(payload.get('active_seconds')),
        )


@dataclass(frozen=True, slots=True)
class UserActivityDocument:
    id: str
    partition_key: str
    application_key: str
    actor_key: str
    provider_key: str
    user_id: str | None
    client_session_id: str
    first_seen_at_utc: datetime
    last_seen_at_utc: datetime
    active_seconds: int
    page_views: int
    visibility_resumes: int
    visibility_state: str
    current_pathname: str
    current_route_key: str
    initial_viewport: Viewport
    last_viewport: Viewport
    initial_screen: Screen
    last_screen: Screen
    routes: Mapping[str, RouteActivity]
    last_sequence: int
    last_event_id: str
    type: str = USER_ACTIVITY_DOCUMENT_TYPE
    schema_version: int = USER_ACTIVITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for label, value in (
            ('User activity id', self.id),
            ('Activity partition key', self.partition_key),
            ('Application key', self.application_key),
            ('Actor key', self.actor_key),
            ('Provider key', self.provider_key),
            ('Client session id', self.client_session_id),
            ('Current route key', self.current_route_key),
        ):
            if not value.strip():
                raise UserActivityError(f'{label} must not be empty')
        if self.first_seen_at_utc.tzinfo is None or self.last_seen_at_utc.tzinfo is None:
            raise UserActivityError('User activity timestamps must be timezone-aware')
        if self.active_seconds < 0 or self.page_views < 0 or self.visibility_resumes < 0:
            raise UserActivityError('User activity counters must not be negative')
        if self.visibility_state not in {'visible', 'hidden'}:
            raise UserActivityError('User activity visibility state is invalid')
        object.__setattr__(self, 'current_pathname', normalize_pathname(self.current_pathname))
        object.__setattr__(self, 'routes', MappingProxyType(dict(self.routes)))

    def to_document(self) -> dict[str, object]:
        return {
            'id': self.id,
            'partition_key': self.partition_key,
            'application_key': self.application_key,
            'actor_key': self.actor_key,
            'provider_key': self.provider_key,
            'user_id': self.user_id,
            'client_session_id': self.client_session_id,
            'first_seen_at_utc': self.first_seen_at_utc.astimezone(UTC).isoformat(),
            'last_seen_at_utc': self.last_seen_at_utc.astimezone(UTC).isoformat(),
            'active_seconds': self.active_seconds,
            'page_views': self.page_views,
            'visibility_resumes': self.visibility_resumes,
            'visibility_state': self.visibility_state,
            'current_pathname': self.current_pathname,
            'current_route_key': self.current_route_key,
            'initial_viewport': self.initial_viewport.to_document(),
            'last_viewport': self.last_viewport.to_document(),
            'initial_screen': self.initial_screen.to_document(),
            'last_screen': self.last_screen.to_document(),
            'routes': {key: value.to_document() for key, value in self.routes.items()},
            'last_sequence': self.last_sequence,
            'last_event_id': self.last_event_id,
            'type': self.type,
            'schema_version': self.schema_version,
        }

    @classmethod
    def from_document(cls, payload: Mapping[str, Any]) -> UserActivityDocument:
        routes_payload = payload.get('routes')
        routes = {
            str(key): RouteActivity.from_value(value)
            for key, value in (
                routes_payload.items() if isinstance(routes_payload, Mapping) else ()
            )
        }
        return cls(
            id=str(payload['id']),
            partition_key=str(payload['partition_key']),
            application_key=str(payload['application_key']),
            actor_key=str(payload['actor_key']),
            provider_key=str(payload['provider_key']),
            user_id=_optional_text(payload.get('user_id')),
            client_session_id=str(payload['client_session_id']),
            first_seen_at_utc=_required_datetime(payload['first_seen_at_utc']),
            last_seen_at_utc=_required_datetime(payload['last_seen_at_utc']),
            active_seconds=_non_negative_int(payload.get('active_seconds')),
            page_views=_non_negative_int(payload.get('page_views')),
            visibility_resumes=_non_negative_int(payload.get('visibility_resumes')),
            visibility_state=str(payload['visibility_state']),
            current_pathname=str(payload['current_pathname']),
            current_route_key=str(payload['current_route_key']),
            initial_viewport=Viewport.from_value(payload.get('initial_viewport')),
            last_viewport=Viewport.from_value(payload.get('last_viewport')),
            initial_screen=Screen.from_value(payload.get('initial_screen')),
            last_screen=Screen.from_value(payload.get('last_screen')),
            routes=routes,
            last_sequence=int(payload['last_sequence']),
            last_event_id=str(payload['last_event_id']),
            type=str(payload.get('type') or USER_ACTIVITY_DOCUMENT_TYPE),
            schema_version=int(payload.get('schema_version') or USER_ACTIVITY_SCHEMA_VERSION),
        )


def actor_key(snapshot: AccessSnapshot) -> str:
    if snapshot.status is not AccessStatus.READY or snapshot.identity is None:
        raise UserActivityError('Ready access snapshot is required for user activity')
    if snapshot.user_id:
        return f'user:{snapshot.user_id}'
    identity = snapshot.identity
    digest = hashlib.sha256(
        f'{identity.provider_key}\x1f{identity.issuer}\x1f{identity.subject_id}'.encode()
    ).hexdigest()[:32]
    return f'identity:{digest}'


def activity_document_id(*, application_key: str, actor: str, client_session_id: str) -> str:
    digest = hashlib.sha256(
        f'{application_key}\x1f{actor}\x1f{client_session_id}'.encode()
    ).hexdigest()
    return f'activity:{digest}'


def normalize_pathname(value: str) -> str:
    parsed = urlsplit(value.strip() or '/')
    if parsed.scheme or parsed.netloc:
        raise UserActivityError('User activity pathname must be a same-origin path')
    path = parsed.path or '/'
    if not path.startswith('/'):
        path = f'/{path}'
    if len(path) > 1:
        path = path.rstrip('/') or '/'
    return path[:512]


def _dimension(value: object) -> int:
    try:
        return max(0, min(100_000, int(value or 0)))
    except TypeError, ValueError:
        return 0


def _ratio(value: object) -> float:
    try:
        ratio = float(value or 1.0)
    except TypeError, ValueError:
        return 1.0
    return ratio if ratio > 0 else 1.0


def _non_negative_int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except TypeError, ValueError:
        return 0


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_datetime(value: object) -> datetime | None:
    if value is None or value == '':
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError as error:
        raise UserActivityError('User activity client timestamp is invalid') from error
    if parsed.tzinfo is None:
        raise UserActivityError('User activity client timestamp must include a timezone')
    return parsed.astimezone(UTC)


def _required_datetime(value: object) -> datetime:
    parsed = _optional_datetime(value)
    if parsed is None:
        raise UserActivityError('User activity timestamp is required')
    return parsed
