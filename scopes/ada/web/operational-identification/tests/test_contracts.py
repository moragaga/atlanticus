from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from ada.web.operational.identification import (
    CATALOG_SOURCE_KEY,
    CosmosOperationalProjectionStore,
    OperationalAssignment,
    OperationalCatalog,
    OperationalIdentificationError,
    OperationalIdentificationService,
    OperationalPersistenceError,
    OperationalReferenceError,
    OperationalSourceService,
    Position,
    assignment_source_key,
)
from ada.web.operational.identification.projection import (
    OperationalProjectionBuilder,
    projection_from_document,
    projection_to_document,
)
from ada.web.operational.identification.source import OperationalSourceCodec
from atlanticus.connectivity.cosmos import CosmosError, CosmosPreconditionFailedError
from atlanticus.web.projection.errors import ProjectionExecutionError
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.errors import SourceConcurrencyError
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
from atlanticus.web.source.models import SourceReleaseId
from atlanticus.web.users.models import EffectiveUser

USER_A = 'user:' + 'a' * 24
USER_B = 'user:' + 'b' * 24


class FakeUsers:
    def __init__(self, *known: str) -> None:
        self.known = set(known)
        self.reads = 0

    def get(self, user_id: str):
        self.reads += 1
        return SimpleNamespace(user_id=user_id) if user_id in self.known else None


class FakeCosmos:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str, str], dict] = {}
        self.fail_writes = False
        self.writes = 0
        self.revisions = 0

    def _key(self, container_name, item_id, partition_key):
        return container_name, item_id, partition_key

    def find_item(self, *, container_name, item_id, partition_key, include_metadata=False):
        entry = self.items.get(self._key(container_name, item_id, partition_key))
        if entry is None:
            return None
        return (
            dict(entry)
            if include_metadata
            else {key: value for key, value in entry.items() if key != '_etag'}
        )

    def create_item(self, *, container_name, item):
        if self.fail_writes:
            raise CosmosError('simulated write failure')
        key = self._key(container_name, item['id'], item['partition_key'])
        if key in self.items:
            raise CosmosPreconditionFailedError('concurrent creation')
        self.revisions += 1
        self.items[key] = {**item, '_etag': f'etag-{self.revisions}'}
        self.writes += 1
        return dict(item)

    def patch_item(self, *, container_name, item_id, partition_key, operations, if_match_etag=None):
        if self.fail_writes:
            raise CosmosError('simulated write failure')
        key = self._key(container_name, item_id, partition_key)
        current = self.items[key]
        if current['_etag'] != if_match_etag:
            raise CosmosPreconditionFailedError('concurrent change')
        next_item = dict(current)
        for operation in operations:
            assert operation.operation == 'set'
            next_item[operation.path[1:]] = operation.value
        self.revisions += 1
        next_item['_etag'] = f'etag-{self.revisions}'
        self.items[key] = next_item
        self.writes += 1
        return {key: value for key, value in next_item.items() if key != '_etag'}


def make_service(tmp_path, users=(USER_A, USER_B)):
    cosmos = FakeCosmos()
    source = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source'))
    projections = CosmosOperationalProjectionStore(client=cosmos, container_name='users-support')
    service = OperationalIdentificationService(
        source_store=source, projections=projections, users=FakeUsers(*users)
    )
    return service, cosmos, source, projections


def test_optional_operational_fields_and_roundtrip():
    assignment = OperationalAssignment(user_id=USER_A)
    assert assignment.area_id is None
    assert assignment.position_id is None
    assert assignment.group_id is None
    assert OperationalAssignment.from_document(assignment.to_document()) == assignment
    assert OperationalCatalog.from_document(OperationalCatalog().to_document()) == (
        OperationalCatalog()
    )


@pytest.mark.parametrize(
    'data',
    [
        {'area_id': 'other'},
        {'group_id': 5},
        {'group_id': True},
        {'position_id': 'bad space'},
    ],
)
def test_assignment_rejects_invalid_values(data):
    with pytest.raises(OperationalIdentificationError):
        OperationalAssignment(user_id=USER_A, **data)


def test_catalog_requires_stable_position_ids_and_unique_labels():
    original = OperationalCatalog(positions=(Position('engineer', 'Ingeniero de sala'),))
    current = OperationalCatalog(positions=(Position('engineer', 'Ingeniero de control'),))
    current.validate_revision(original)
    with pytest.raises(OperationalReferenceError):
        OperationalCatalog().validate_revision(original)
    with pytest.raises(OperationalIdentificationError):
        OperationalCatalog(
            positions=(
                Position('eng', 'Ingeniero'),
                Position('superintendent', 'ingeniero'),
            )
        )


def test_source_codec_is_deterministic_and_rejects_wrong_resources():
    codec = OperationalSourceCodec()
    first = codec.encode(OperationalAssignment(user_id=USER_A, group_id=4), actor='operator')
    second = codec.encode(OperationalAssignment(user_id=USER_A, group_id=4), actor='operator')
    assert first == second
    assert codec.decode((first,)) == OperationalAssignment(user_id=USER_A, group_id=4)
    with pytest.raises(OperationalIdentificationError):
        codec.decode(())


def test_source_per_user_does_not_overwrite_other_user(tmp_path):
    _, _, store, _ = make_service(tmp_path)
    source = OperationalSourceService(store=store)
    for user, group in ((USER_A, 1), (USER_B, 3)):
        key = assignment_source_key(user)
        saved = source.publish(
            OperationalAssignment(user_id=user, group_id=group),
            actor='manager',
            expected=source.snapshot(key),
        )
        assert source.read(key, saved.release.release_ref).group_id == group
    assert source.current(assignment_source_key(USER_A))[1].group_id == 1
    assert source.current(assignment_source_key(USER_B))[1].group_id == 3


def test_source_rejects_stale_save(tmp_path):
    _, _, store, _ = make_service(tmp_path)
    source = OperationalSourceService(store=store)
    key = assignment_source_key(USER_A)
    original = source.snapshot(key)
    source.publish(OperationalAssignment(user_id=USER_A), actor='manager', expected=original)
    with pytest.raises(SourceConcurrencyError):
        source.publish(
            OperationalAssignment(user_id=USER_A, area_id='mina'),
            actor='manager',
            expected=original,
        )


def test_manager_contract_and_individual_projection(tmp_path):
    service, cosmos, _, projections = make_service(tmp_path)
    catalog_snapshot, catalog = service.catalog_for_edit()
    assert catalog.positions == ()
    with_positions = OperationalCatalog(
        (
            Position('engineer', 'Ingeniero de sala'),
            Position('superintendent', 'Superintendente'),
        )
    )
    service.publish_catalog(with_positions, actor='operator', expected=catalog_snapshot)
    assert service.catalog_for_read() == OperationalCatalog()
    service.project_current(CATALOG_SOURCE_KEY)
    assert service.catalog_for_read() == with_positions

    for user, group in ((USER_A, 1), (USER_B, 4)):
        snapshot, _ = service.assignment_for_edit(user)
        service.publish_assignment(
            OperationalAssignment(
                user_id=user,
                area_id='mina',
                position_id='engineer',
                group_id=group,
            ),
            actor='operator',
            expected=snapshot,
        )
        service.project_current(assignment_source_key(user))
    assert service.assignment_for_read(USER_A).group_id == 1
    assert service.assignment_for_read(USER_B).group_id == 4
    assert len(cosmos.items) == 3
    assert all(key[0] == 'users-support' for key in cosmos.items)
    assert projections.get_active(assignment_source_key(USER_A)).payload.user_id == USER_A


def test_missing_promotion_rejected_and_no_source_written(tmp_path):
    service, _, store, _ = make_service(tmp_path, users=(USER_A,))
    source = OperationalSourceService(store=store)
    with pytest.raises(OperationalReferenceError, match='promoted'):
        service.assignment_for_edit(USER_B)
    with pytest.raises(OperationalReferenceError, match='promoted'):
        service.publish_assignment(
            OperationalAssignment(user_id=USER_B),
            actor='manager',
            expected=source.snapshot(assignment_source_key(USER_B)),
        )
    assert source.snapshot(assignment_source_key(USER_B)).current is None


def test_deactivated_position_retains_existing_assignment_only(tmp_path):
    service, _, _, _ = make_service(tmp_path)
    original, _ = service.catalog_for_edit()
    service.publish_catalog(
        OperationalCatalog((Position('engineer', 'Ingeniero'),)),
        actor='manager',
        expected=original,
    )
    initial, _ = service.assignment_for_edit(USER_A)
    service.publish_assignment(
        OperationalAssignment(user_id=USER_A, position_id='engineer'),
        actor='manager',
        expected=initial,
    )
    revised, _ = service.catalog_for_edit()
    service.publish_catalog(
        OperationalCatalog((Position('engineer', 'Ingeniero', active=False),)),
        actor='manager',
        expected=revised,
    )
    current, _ = service.assignment_for_edit(USER_A)
    service.publish_assignment(
        OperationalAssignment(user_id=USER_A, position_id='engineer', group_id=3),
        actor='manager',
        expected=current,
    )
    new_user, _ = service.assignment_for_edit(USER_B)
    with pytest.raises(OperationalReferenceError, match='unavailable'):
        service.publish_assignment(
            OperationalAssignment(user_id=USER_B, position_id='engineer'),
            actor='manager',
            expected=new_user,
        )


def test_failed_projection_can_be_retried_from_durable_source(tmp_path):
    service, cosmos, _, _ = make_service(tmp_path)
    expected, _ = service.assignment_for_edit(USER_A)
    published = service.publish_assignment(
        OperationalAssignment(user_id=USER_A, area_id='planta'),
        actor='manager',
        expected=expected,
    )
    cosmos.fail_writes = True
    with pytest.raises(ProjectionExecutionError):
        service.project_current(assignment_source_key(USER_A))
    source_state, source_value = service.assignment_for_edit(USER_A)
    assert source_state.current.release_ref == published.release.release_ref
    assert source_value.area_id == 'planta'
    cosmos.fail_writes = False
    service.project_current(assignment_source_key(USER_A))
    assert service.assignment_for_read(USER_A).area_id == 'planta'
    writes = cosmos.writes
    service.project_current(assignment_source_key(USER_A))
    assert cosmos.writes == writes


def test_projection_update_uses_etag_and_refuses_stale_replay(tmp_path):
    service, cosmos, source, projections = make_service(tmp_path)
    previous, _ = service.assignment_for_edit(USER_A)
    first = service.publish_assignment(
        OperationalAssignment(user_id=USER_A, group_id=1),
        actor='manager',
        expected=previous,
    )
    service.project_current(assignment_source_key(USER_A))
    newer, _ = service.assignment_for_edit(USER_A)
    second = service.publish_assignment(
        OperationalAssignment(user_id=USER_A, group_id=2),
        actor='manager',
        expected=newer,
    )
    service.project_current(assignment_source_key(USER_A))
    assert service.assignment_for_read(USER_A).group_id == 2
    builder = OperationalProjectionBuilder()
    metadata, resources = source.read_release(
        assignment_source_key(USER_A), first.release.release_ref
    )
    stale = ProjectionRecord(
        source_key=metadata.source_key,
        source_release_id=first.release.release_ref.release_id,
        source_published_at_utc=first.release.release_ref.published_at_utc,
        projected_at_utc=datetime.now(UTC),
        payload=builder.build(
            target=ProjectionTarget(metadata.source_key, first.release.release_ref),
            release=metadata,
            resources=resources,
        ),
    )
    with pytest.raises(OperationalPersistenceError, match='newer'):
        projections.replace_active(stale)
    assert service.assignment_for_read(USER_A).group_id == 2
    assert second.release.release_ref.published_at_utc >= first.release.release_ref.published_at_utc


def test_projection_codec_rejects_cross_document_payload():
    target = assignment_source_key(USER_A)
    now = datetime(2026, 9, 28, tzinfo=UTC)
    original = ProjectionRecord(
        source_key=target,
        source_release_id=SourceReleaseId('r1'),
        source_published_at_utc=now,
        projected_at_utc=now + timedelta(seconds=1),
        payload=OperationalAssignment(user_id=USER_A, group_id=2),
    )
    document = projection_to_document(original, item_id='test-projection')
    assert projection_from_document(document) == original
    wrong = {**document, 'user_id': USER_B}
    with pytest.raises(OperationalIdentificationError):
        projection_to_document(
            ProjectionRecord(
                source_key=target,
                source_release_id=SourceReleaseId('r1'),
                source_published_at_utc=now,
                projected_at_utc=now,
                payload=OperationalAssignment(user_id=USER_B),
            ),
            item_id='test-projection',
        )
    with pytest.raises(OperationalIdentificationError):
        projection_from_document(wrong)
    client = FakeCosmos()
    projection = CosmosOperationalProjectionStore(client=client, container_name='users-support')
    projection.replace_active(original)
    stored = next(iter(client.items.values()))
    stored['user_id'] = USER_B
    with pytest.raises(OperationalIdentificationError):
        projection.get_active(target)


def test_resolved_session_user_reads_projection_without_requerying_global_users(tmp_path):
    users = FakeUsers(USER_A)
    cosmos = FakeCosmos()
    source = LocalSourceStore(LocalSourceSettings(root=tmp_path / 'source'))
    projections = CosmosOperationalProjectionStore(client=cosmos, container_name='users-support')
    service = OperationalIdentificationService(
        source_store=source,
        projections=projections,
        users=users,
    )
    snapshot, _ = service.assignment_for_edit(USER_A)
    service.publish_assignment(
        OperationalAssignment(user_id=USER_A, group_id=2),
        actor='manager',
        expected=snapshot,
    )
    service.project_current(assignment_source_key(USER_A))
    before = users.reads
    resolved = EffectiveUser(
        user_id=USER_A,
        subject_id='subject-a',
        display_name='Operator A',
        email=None,
        enabled=True,
        avatar_text='OA',
        profile_key='basic',
    )
    assert service.assignment_for_resolved_user(resolved).group_id == 2
    assert users.reads == before
    with pytest.raises(OperationalReferenceError):
        service.assignment_for_resolved_user(
            EffectiveUser(
                user_id=USER_A,
                subject_id='subject-a',
                display_name='Operator A',
                email=None,
                enabled=False,
                avatar_text='OA',
                profile_key='basic',
            )
        )


def test_operational_documents_do_not_modify_other_shared_support_records(tmp_path):
    service, cosmos, _, _ = make_service(tmp_path)
    existing = {
        'id': 'profile-existing',
        'partition_key': 'profiles-configuration',
        'document_type': 'atlanticus_profiles_projection_record',
        'payload': {'profiles': []},
        '_etag': 'profile-etag',
    }
    key = ('users-support', 'profile-existing', 'profiles-configuration')
    cosmos.items[key] = dict(existing)
    current, _ = service.assignment_for_edit(USER_A)
    service.publish_assignment(
        OperationalAssignment(user_id=USER_A, group_id=1),
        actor='manager',
        expected=current,
    )
    service.project_current(assignment_source_key(USER_A))
    assert cosmos.items[key] == existing
    assert len(cosmos.items) == 2


def test_projection_retries_optimistic_conflict(tmp_path):
    service, cosmos, _, _ = make_service(tmp_path)
    first_snapshot, _ = service.assignment_for_edit(USER_A)
    service.publish_assignment(
        OperationalAssignment(user_id=USER_A, group_id=1),
        actor='manager',
        expected=first_snapshot,
    )
    service.project_current(assignment_source_key(USER_A))
    second_snapshot, _ = service.assignment_for_edit(USER_A)
    service.publish_assignment(
        OperationalAssignment(user_id=USER_A, group_id=2),
        actor='manager',
        expected=second_snapshot,
    )
    original = cosmos.patch_item
    attempts = 0

    def transient(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise CosmosPreconditionFailedError('ETag conflict')
        return original(*args, **kwargs)

    cosmos.patch_item = transient
    service.project_current(assignment_source_key(USER_A))
    assert attempts == 2
    assert service.assignment_for_read(USER_A).group_id == 2
