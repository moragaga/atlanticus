from datetime import UTC, datetime

import pytest

from atlanticus.web.users.activity.adapters.cosmos import CosmosUserActivityRepository
from atlanticus.web.users.activity.contracts import StoredUserActivity
from atlanticus.web.users.activity.errors import UserActivityConflictError
from atlanticus.web.users.activity.models import (
    RouteActivity,
    Screen,
    UserActivityDocument,
    Viewport,
)


class _CosmosError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(str(status_code))
        self.status_code = status_code


class _Container:
    def __init__(self) -> None:
        self.item = None
        self.etag = '1'

    def read_item(self, *, item: str, partition_key: str):
        if (
            self.item is None
            or self.item['id'] != item
            or self.item['partition_key'] != partition_key
        ):
            raise _CosmosError(404)
        return {**self.item, '_etag': self.etag}

    def create_item(self, *, body):
        if self.item is not None:
            raise _CosmosError(409)
        self.item = dict(body)
        return {**self.item, '_etag': self.etag}

    def replace_item(self, *, item: str, body, etag: str, match_condition: str):
        assert match_condition == 'IfNotModified'
        if etag != self.etag:
            raise _CosmosError(412)
        self.item = dict(body)
        self.etag = str(int(self.etag) + 1)
        return {**self.item, '_etag': self.etag}


def _document() -> UserActivityDocument:
    now = datetime(2026, 8, 31, tzinfo=UTC)
    return UserActivityDocument(
        id='activity:1',
        partition_key='user:1',
        application_key='app',
        actor_key='user:1',
        provider_key='entra',
        user_id='1',
        client_session_id='session',
        first_seen_at_utc=now,
        last_seen_at_utc=now,
        active_seconds=0,
        page_views=1,
        visibility_resumes=0,
        visibility_state='visible',
        current_pathname='/',
        current_route_key='home',
        initial_viewport=Viewport(100, 100),
        last_viewport=Viewport(100, 100),
        initial_screen=Screen(100, 100, 1.0),
        last_screen=Screen(100, 100, 1.0),
        routes={'home': RouteActivity(pathname='/', views=1)},
        last_sequence=1,
        last_event_id='event-1',
    )


def test_cosmos_adapter_uses_partition_key_and_etag() -> None:
    container = _Container()
    repository = CosmosUserActivityRepository(container)

    created = repository.save(_document(), expected_revision=None)
    loaded = repository.load(document_id='activity:1', partition_key='user:1')
    replaced = repository.save(_document(), expected_revision=created.revision)

    assert isinstance(loaded, StoredUserActivity)
    assert loaded.document.id == 'activity:1'
    assert replaced.revision == '2'


def test_cosmos_adapter_maps_precondition_failure_to_conflict() -> None:
    container = _Container()
    repository = CosmosUserActivityRepository(container)
    repository.save(_document(), expected_revision=None)

    with pytest.raises(UserActivityConflictError, match='revision conflict'):
        repository.save(_document(), expected_revision='stale')
