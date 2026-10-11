from dataclasses import replace
from types import SimpleNamespace

import pytest

from ada.web.access.configuration import AdaAccessConfiguration
from ada.web.access.models import ProfileAccessGrant
from ada.web.application.generic.users_materialization import (
    AdaUsersRuntimeMaterializer,
    UsersMaterializationError,
)
from ada.web.operational.identification import OperationalAssignment, OperationalCatalog, Position
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    ToolMembershipSnapshot,
    ToolUserMembership,
    UserIdentity,
    UsersRegistrySnapshot,
)


def _identity(subject: str) -> UserIdentity:
    return UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id=subject),
        issuer='issuer',
        subject_id=subject,
        display_name=subject,
    )


class _Source:
    def __init__(self, ref: str) -> None:
        self.ref = ref

    def get_current(self, _key):
        return SimpleNamespace(current=SimpleNamespace(release_ref=self.ref))


class _Projection:
    def __init__(self, record, *, assignments=None) -> None:
        self.record = record
        self.assignments = assignments or {}

    def get_active(self, key):
        if key.value.startswith('ada-operational-user:'):
            return self.assignments.get(key.value)
        return self.record


class _Value:
    def __init__(self, value) -> None:
        self.value = value

    def load(self):
        return self.value


class _Operations:
    def __init__(self, assignments: dict[str, OperationalAssignment]) -> None:
        self.assignments = assignments
        self.snapshots = {
            key: SimpleNamespace(current=SimpleNamespace(release_ref='assignment-1'))
            for key in assignments
        }
        self.catalog_snapshot = SimpleNamespace(current=SimpleNamespace(release_ref='catalog-1'))

    def snapshot(self, key):
        if key.value == 'ada-operational-catalog':
            return self.catalog_snapshot
        return self.snapshots.setdefault(key.value, SimpleNamespace(current=None))

    def current(self, key):
        raise AssertionError('Materialization must use the projected assignment')


class _Writer:
    def __init__(self) -> None:
        self.users = {}

    def upsert_user(self, user):
        self.users[user.user_id] = user
        return user


def _setup(*, profile_ref='profiles-1', access_ref='access-1', catalog_ref='catalog-1'):
    identities = (_identity('alice'), _identity('bob'))
    registry = UsersRegistrySnapshot(users=identities)
    memberships = ToolMembershipSnapshot(
        memberships=tuple(ToolUserMembership(user_id=item.user_id, profile_key='basic') for item in identities)
    )
    profiles = ProfileCatalog()
    access = AdaAccessConfiguration(
        access_keys=('dashboard.view', 'reports.read'),
        profile_access=(ProfileAccessGrant(profile_key='basic', access_keys=('reports.read', 'dashboard.view')),),
    )
    catalog = OperationalCatalog(positions=(Position(id='operator', label='Operator'),))
    profiles_record = SimpleNamespace(source_release=profile_ref, target='profiles-target', payload=profiles)
    access_record = SimpleNamespace(
        source_release=access_ref,
        dependencies=('profiles-target',),
        payload=access,
    )
    catalog_record = SimpleNamespace(source_release=catalog_ref, payload=catalog)
    ops = _Operations({
        f'ada-operational-user:{identities[0].user_id}': OperationalAssignment(
            user_id=identities[0].user_id,
            area_id='mina',
            position_id='operator',
            group_id=2,
        )
    })
    stores = SimpleNamespace(
        users_registry=_Value(registry),
        users_memberships=_Value(memberships),
        profiles_source=_Source(profile_ref),
        profiles=_Projection(profiles_record),
        access_source=_Source(access_ref),
        access=_Projection(access_record),
        operational_source=object(),
        operational=_Projection(
            catalog_record,
            assignments={
                key: SimpleNamespace(source_release='assignment-1', payload=value)
                for key, value in ops.assignments.items()
            },
        ),
    )
    materializer = AdaUsersRuntimeMaterializer(stores=stores)
    materializer._operational_source = ops
    return materializer, stores, ops, identities


def test_materialization_resolves_access_and_operational_references_from_current_sources():
    service, _stores, _ops, identities = _setup()

    user = service.materialize_user(identities[0].user_id)

    assert user.identity == identities[0]
    assert user.profile.id == 'basic'
    assert user.access_keys == ('dashboard.view', 'reports.read')
    assert user.operational.area.label == 'Mina'
    assert user.operational.position.label == 'Operator'
    assert user.operational.group.label == 'Grupo 2'
    assert type(user).from_document(user.to_document()) == user


def test_materialization_without_assignment_is_valid_and_full_set_matches_single_users():
    service, _stores, _ops, identities = _setup()

    users = service.materialize_all()

    assert users == tuple(sorted((service.materialize_user(i.user_id) for i in identities), key=lambda u: u.user_id))
    assert next(u for u in users if u.user_id == identities[1].user_id).operational.position is None


def test_publish_one_does_not_replace_other_runtime_users():
    service, _stores, _ops, identities = _setup()
    writer = _Writer()
    first = service.publish_user(identities[0].user_id, writer=writer)
    second = service.publish_user(identities[1].user_id, writer=writer)
    assert len(writer.users) == 2
    assert writer.users[first.user_id] == first
    assert writer.users[second.user_id] == second


def test_missing_global_identity_fails_without_materializing_user():
    service, stores, _ops, identities = _setup()
    stores.users_registry.value = UsersRegistrySnapshot(users=(identities[1],))

    with pytest.raises(UsersMaterializationError, match='global identity'):
        service.materialize_user(identities[0].user_id)


def test_unprojected_access_changes_fail_closed():
    service, stores, _ops, identities = _setup()
    stores.access_source.ref = 'access-2'
    with pytest.raises(UsersMaterializationError, match='Access projection'):
        service.materialize_user(identities[0].user_id)


def test_source_change_during_materialization_is_detected():
    service, stores, _ops, identities = _setup()
    original = stores.users_memberships.value

    class UpdatingRegistry(_Value):
        def __init__(self):
            self.count = 0

        def load(self):
            self.count += 1
            return original if self.count == 1 else replace(original, version='changed')

    stores.users_memberships = UpdatingRegistry()

    with pytest.raises(UsersMaterializationError, match='changed during resolution'):
        service.materialize_user(identities[0].user_id)


def test_operational_catalog_behind_source_fails_closed():
    service, stores, _ops, identities = _setup()
    stores.operational.record.source_release = 'catalog-older'
    with pytest.raises(UsersMaterializationError, match='Operational catalog'):
        service.materialize_user(identities[0].user_id)


def test_stale_operational_assignment_projection_fails_closed():
    service, stores, _ops, identities = _setup()
    key = f'ada-operational-user:{identities[0].user_id}'
    stores.operational.assignments[key].source_release = 'outdated'
    with pytest.raises(
        UsersMaterializationError, match='current Operational assignment projection'
    ):
        service.materialize_user(identities[0].user_id)


def test_missing_operational_assignment_projection_fails_closed():
    service, stores, _ops, identities = _setup()
    stores.operational.assignments.clear()
    with pytest.raises(
        UsersMaterializationError, match='current Operational assignment projection'
    ):
        service.materialize_user(identities[0].user_id)


def test_orphan_operational_assignment_projection_fails_closed():
    service, _stores, ops, identities = _setup()
    ops.snapshots[f'ada-operational-user:{identities[0].user_id}'] = SimpleNamespace(current=None)
    with pytest.raises(UsersMaterializationError, match='projection has no source'):
        service.materialize_user(identities[0].user_id)


def test_projected_assignment_change_during_materialization_fails_closed():
    service, stores, _ops, identities = _setup()
    key = f'ada-operational-user:{identities[0].user_id}'
    projection = stores.operational
    before = projection.assignments[key]

    class ChangingProjection(_Projection):
        def __init__(self):
            super().__init__(projection.record, assignments=dict(projection.assignments))
            self.reads = 0

        def get_active(self, source_key):
            result = super().get_active(source_key)
            if source_key.value == key:
                self.reads += 1
                if self.reads == 2:
                    return SimpleNamespace(source_release='assignment-2', payload=before.payload)
            return result

    stores.operational = ChangingProjection()
    with pytest.raises(UsersMaterializationError, match='changed during resolution'):
        service.materialize_user(identities[0].user_id)


def test_disabled_membership_is_materialized_without_granting_enabled_status():
    service, stores, _ops, identities = _setup()
    memberships = list(stores.users_memberships.value.memberships)
    memberships[0] = replace(memberships[0], enabled=False)
    stores.users_memberships.value = ToolMembershipSnapshot(memberships=tuple(memberships))
    user = service.materialize_user(identities[0].user_id)
    assert user.enabled is False
