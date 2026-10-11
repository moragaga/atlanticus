from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

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
    projection_from_document,
    projection_to_document,
)
from ada.web.operational.identification.source import OperationalSourceCodec
from atlanticus.connectivity.cosmos import CosmosError, CosmosPreconditionFailedError
from atlanticus.web.profiles.models import BASIC_PROFILE
from atlanticus.web.projection.errors import ProjectionExecutionError
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.errors import SourceConcurrencyError
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
from atlanticus.web.source.models import SourceReleaseId
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    RuntimeOperational,
    RuntimeOperationalReference,
    RuntimeProfile,
    RuntimeUser,
    ToolMembershipSnapshot,
    ToolUserMembership,
    UserIdentity,
)

USER_A = 'user:' + 'a' * 24
USER_B = 'user:' + 'b' * 24


class FakeMemberships:
    def __init__(self, *known: str) -> None:
        self.snapshot = ToolMembershipSnapshot(
            memberships=tuple(
                ToolUserMembership(user_id=user_id, profile_key='basic')
                for user_id in known
            )
        )
        self.reads = 0

    def load(self) -> ToolMembershipSnapshot:
        self.reads += 1
        return self.snapshot


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
    memberships = FakeMemberships(*users)
    service = OperationalIdentificationService(
        source_store=source,
        projections=projections,
        memberships=memberships,
    )
    return service, cosmos, source, projections, memberships


def publish_catalog(service, *, positions=()):
    snapshot, _ = service.catalog_for_edit()
    service.publish_catalog(OperationalCatalog(positions=positions), actor='manager', expected=snapshot)
    return service.project_current(CATALOG_SOURCE_KEY)


def publish_assignment(service, user_id, **values):
    snapshot, _ = service.assignment_for_edit(user_id)
    return service.publish_assignment(
        OperationalAssignment(user_id=user_id, **values),
        actor='manager',
        expected=snapshot,
    )


def test_optional_operational_fields_and_roundtrip():
    assignment = OperationalAssignment(user_id=USER_A)
    assert assignment.area_id is None
    assert assignment.position_id is None
    assert assignment.group_id is None
    assert OperationalAssignment.from_document(assignment.to_document()) == assignment
    assert OperationalCatalog.from_document(OperationalCatalog().to_document()) == OperationalCatalog()


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
    updated = OperationalCatalog(positions=(Position('engineer', 'Ingeniero de control'),))
    updated.validate_revision(original)
    with pytest.raises(OperationalReferenceError):
        OperationalCatalog().validate_revision(original)
    with pytest.raises(OperationalIdentificationError):
        OperationalCatalog(
            positions=(Position('eng', 'Ingeniero'), Position('superintendent', 'ingeniero'))
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
    _, _, store, _, _ = make_service(tmp_path)
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
    _, _, store, _, _ = make_service(tmp_path)
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


def test_catalog_only_is_projected_and_assignment_is_owned_by_source(tmp_path):
    service, cosmos, source, projections, _ = make_service(tmp_path)
    positions = (Position('engineer', 'Ingeniero de sala'),)
    assert service.catalog_for_read() == OperationalCatalog()
    publish_catalog(service, positions=positions)
    assert service.catalog_for_read() == OperationalCatalog(positions=positions)
    for user, group in ((USER_A, 1), (USER_B, 4)):
        publish_assignment(service, user, area_id='mina', position_id='engineer', group_id=group)
        assert service.assignment_for_read(user).group_id == group
        assert source.get_current(assignment_source_key(user)).current is not None
        assert projections.get_active(assignment_source_key(user)) is None
        with pytest.raises(OperationalReferenceError, match='not projected'):
            service.project_current(assignment_source_key(user))
        with pytest.raises(OperationalReferenceError, match='not projected'):
            service.projection_status(assignment_source_key(user))
    assert len(cosmos.items) == 1
    assert {entry['document_type'] for entry in cosmos.items.values()} == {
        'ada_operational_catalog_projection'
    }


def test_missing_membership_rejected_without_source_write(tmp_path):
    service, _, store, _, _ = make_service(tmp_path, users=(USER_A,))
    source = OperationalSourceService(store=store)
    with pytest.raises(OperationalReferenceError, match='Tool membership'):
        service.assignment_for_edit(USER_B)
    with pytest.raises(OperationalReferenceError, match='Tool membership'):
        service.publish_assignment(
            OperationalAssignment(user_id=USER_B),
            actor='manager',
            expected=source.snapshot(assignment_source_key(USER_B)),
        )
    assert source.snapshot(assignment_source_key(USER_B)).current is None


def test_deactivated_position_retains_existing_assignment_only(tmp_path):
    service, _, _, _, _ = make_service(tmp_path)
    publish_catalog(service, positions=(Position('engineer', 'Ingeniero'),))
    publish_assignment(service, USER_A, position_id='engineer')
    snapshot, _ = service.catalog_for_edit()
    service.publish_catalog(
        OperationalCatalog((Position('engineer', 'Ingeniero', active=False),)),
        actor='manager',
        expected=snapshot,
    )
    publish_assignment(service, USER_A, position_id='engineer', group_id=3)
    with pytest.raises(OperationalReferenceError, match='outdated'):
        publish_assignment(service, USER_B, position_id='engineer')
    service.project_current(CATALOG_SOURCE_KEY)
    with pytest.raises(OperationalReferenceError, match='unavailable'):
        publish_assignment(service, USER_B, position_id='engineer')


def test_assignment_does_not_depend_on_cosmos_writes(tmp_path):
    service, cosmos, source, _, _ = make_service(tmp_path)
    cosmos.fail_writes = True
    result = publish_assignment(service, USER_A, area_id='planta')
    assert service.assignment_for_read(USER_A).area_id == 'planta'
    assert source.get_current(assignment_source_key(USER_A)).current.release_ref == result.release.release_ref
    with pytest.raises(OperationalReferenceError, match='not projected'):
        service.project_current(assignment_source_key(USER_A))
    assert cosmos.writes == 0


def test_catalog_projection_failure_can_retry_without_rewriting_source(tmp_path):
    service, cosmos, source, _, _ = make_service(tmp_path)
    snapshot, _ = service.catalog_for_edit()
    published = service.publish_catalog(
        OperationalCatalog(positions=(Position('operator', 'Operador'),)),
        actor='manager',
        expected=snapshot,
    )
    cosmos.fail_writes = True
    with pytest.raises(ProjectionExecutionError):
        service.project_current(CATALOG_SOURCE_KEY)
    assert source.get_current(CATALOG_SOURCE_KEY).current.release_ref == published.release.release_ref
    cosmos.fail_writes = False
    assert service.project_current(CATALOG_SOURCE_KEY).payload.position('operator') is not None
    writes = cosmos.writes
    service.project_current(CATALOG_SOURCE_KEY)
    assert cosmos.writes == writes


def test_catalog_projection_uses_etag_and_rejects_stale_replay(tmp_path):
    service, cosmos, source, projections, _ = make_service(tmp_path)
    previous, _ = service.catalog_for_edit()
    first = service.publish_catalog(
        OperationalCatalog(positions=(Position('engineer', 'Ingeniero'),)),
        actor='manager',
        expected=previous,
    )
    service.project_current(CATALOG_SOURCE_KEY)
    newer, _ = service.catalog_for_edit()
    second = service.publish_catalog(
        OperationalCatalog(positions=(Position('engineer', 'Ingeniero senior'),)),
        actor='manager',
        expected=newer,
    )
    service.project_current(CATALOG_SOURCE_KEY)
    assert service.catalog_for_read().position('engineer').label == 'Ingeniero senior'
    metadata, resources = source.read_release(CATALOG_SOURCE_KEY, first.release.release_ref)
    stale = ProjectionRecord(
        source_key=metadata.source_key,
        source_release_id=first.release.release_ref.release_id,
        source_published_at_utc=first.release.release_ref.published_at_utc,
        projected_at_utc=datetime.now(UTC),
        payload=OperationalSourceCodec().decode(resources),
    )
    with pytest.raises(OperationalPersistenceError, match='newer'):
        projections.replace_active(stale)
    assert service.catalog_for_read().position('engineer').label == 'Ingeniero senior'
    assert second.release.release_ref.published_at_utc >= first.release.release_ref.published_at_utc
    assert cosmos.writes == 2


def test_catalog_projection_codec_detects_invalid_document():
    now = datetime(2026, 9, 28, tzinfo=UTC)
    record = ProjectionRecord(
        source_key=CATALOG_SOURCE_KEY,
        source_release_id=SourceReleaseId('r1'),
        source_published_at_utc=now,
        projected_at_utc=now + timedelta(seconds=1),
        payload=OperationalCatalog(positions=(Position('operator', 'Operador'),)),
    )
    document = projection_to_document(record, item_id='catalog-projection')
    assert projection_from_document(document) == record
    with pytest.raises(OperationalIdentificationError):
        projection_from_document({**document, 'document_type': 'not-catalog'})
    with pytest.raises(OperationalIdentificationError):
        projection_to_document(
            replace(record, payload=OperationalAssignment(user_id=USER_A)),
            item_id='catalog-projection',
        )


def test_resolved_runtime_user_reads_its_snapshot_without_source_or_membership_lookup(tmp_path):
    user_id = build_user_key(issuer='issuer', subject_id='operator-a')
    service, _, _, _, memberships = make_service(tmp_path, users=(user_id,))
    publish_assignment(service, user_id, group_id=2)
    identity = UserIdentity(
        user_id=user_id,
        issuer='issuer',
        subject_id='operator-a',
        display_name='Operator A',
    )
    resolved = RuntimeUser(
        identity=identity,
        enabled=True,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE),
    )
    before = memberships.reads
    assert service.assignment_for_resolved_user(resolved).group_id is None
    enriched = replace(
        resolved,
        operational=RuntimeOperational(
            group=RuntimeOperationalReference(id=2, label='Grupo 2'),
        ),
    )
    assert service.assignment_for_resolved_user(enriched).group_id == 2
    assert memberships.reads == before
    with pytest.raises(OperationalReferenceError, match='not authorized'):
        service.assignment_for_resolved_user(replace(enriched, enabled=False))


def test_catalog_projection_does_not_modify_other_support_records(tmp_path):
    service, cosmos, _, _, _ = make_service(tmp_path)
    existing = {
        'id': 'profile-existing',
        'partition_key': 'profiles-configuration',
        'document_type': 'atlanticus_profiles_projection_record',
        'payload': {'profiles': []},
        '_etag': 'profile-etag',
    }
    key = ('users-support', 'profile-existing', 'profiles-configuration')
    cosmos.items[key] = dict(existing)
    publish_catalog(service)
    publish_assignment(service, USER_A, group_id=1)
    assert cosmos.items[key] == existing
    assert len(cosmos.items) == 2
    assert all(
        entry['document_type'] != 'ada_operational_assignment_projection'
        for entry in cosmos.items.values()
    )


def test_catalog_projection_retries_optimistic_conflict(tmp_path):
    service, cosmos, _, _, _ = make_service(tmp_path)
    publish_catalog(service, positions=(Position('engineer', 'Ingeniero'),))
    original, _ = service.catalog_for_edit()
    service.publish_catalog(
        OperationalCatalog(positions=(Position('engineer', 'Ingeniero senior'),)),
        actor='manager',
        expected=original,
    )
    original_patch = cosmos.patch_item
    attempts = 0

    def transient(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise CosmosPreconditionFailedError('ETag conflict')
        return original_patch(*args, **kwargs)

    cosmos.patch_item = transient
    service.project_current(CATALOG_SOURCE_KEY)
    assert attempts == 2
    assert service.catalog_for_read().position('engineer').label == 'Ingeniero senior'
