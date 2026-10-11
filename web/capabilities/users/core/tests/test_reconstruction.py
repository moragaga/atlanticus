from dataclasses import replace

import pytest

from atlanticus.web.profiles.models import (
    BASIC_PROFILE,
    GUEST_PROFILE,
    LOCAL_PROFILE,
    ROOT_PROFILE,
    ProfileCatalog,
)
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    RuntimeOperational,
    RuntimeOperationalReference,
    RuntimeProfile,
    RuntimeUser,
    ToolMembershipSnapshot,
    ToolUserMembership,
    UserIdentity,
    UsersRegistrySnapshot,
)
from atlanticus.web.users.reconstruction import (
    UsersReconstructionConflictError,
    UsersReconstructionWorkflow,
)


class Registry:
    def __init__(self, identities):
        self.identities = tuple(identities)

    def load(self):
        return UsersRegistrySnapshot(users=self.identities)


class Memberships:
    def __init__(self, memberships):
        self.memberships = tuple(memberships)

    def load(self):
        return ToolMembershipSnapshot(memberships=self.memberships)


class Runtime:
    def __init__(self, users=()):
        self.users = {user.user_id: user for user in users}
        self.published = []

    def list_users(self):
        return tuple(self.users.values())

    def upsert_base_user(self, user):
        previous = self.users.get(user.user_id)
        if previous is not None:
            if (previous.issuer, previous.subject_id) != (user.issuer, user.subject_id):
                raise ValueError('Runtime identity cannot change')
            user = replace(
                user,
                access_keys=previous.access_keys,
                operational=previous.operational,
            )
        self.users[user.user_id] = user
        self.published.append(user.user_id)
        return user


def identity(subject):
    issuer = 'issuer'
    return UserIdentity(
        user_id=build_user_key(issuer=issuer, subject_id=subject),
        issuer=issuer,
        subject_id=subject,
        display_name=subject,
    )


def membership(user, profile='basic'):
    return ToolUserMembership(user_id=user.user_id, profile_key=profile)


def runtime_user(user, *, profile=BASIC_PROFILE, enabled=True):
    return RuntimeUser(
        identity=user,
        enabled=enabled,
        profile=RuntimeProfile.from_profile(profile),
        access_keys=('dashboard.view',),
        operational=RuntimeOperational(
            area=RuntimeOperationalReference(id=1, label='Plant'),
        ),
    )


def workflow(identities, memberships, runtime):
    return UsersReconstructionWorkflow(
        registry=Registry(identities),
        memberships=memberships,
        profiles=lambda: ProfileCatalog(),
        runtime=runtime,
        writer=runtime,
    )


def test_reconstructs_users_from_registry_memberships_profiles_without_snapshots():
    person = identity('user-1')
    memberships = Memberships((membership(person),))
    runtime = Runtime()
    service = workflow((person,), memberships, runtime)

    preview = service.inspect()
    assert preview.create_ids == (person.user_id,)
    assert service.apply(preview).has_changes is False
    assert runtime.users[person.user_id].profile.id == BASIC_PROFILE.key
    assert runtime.users[person.user_id].enabled is True
    assert runtime.published == [person.user_id]

    service.apply(service.inspect())
    assert runtime.published == [person.user_id]


def test_reconstructing_base_preserves_access_and_operational_data():
    person = identity('user-2')
    memberships = Memberships((membership(person, 'root'),))
    initial = runtime_user(person, profile=BASIC_PROFILE)
    runtime = Runtime((initial,))
    service = workflow((person,), memberships, runtime)

    preview = service.inspect()
    assert preview.update_ids == (person.user_id,)
    service.apply(preview)

    current = runtime.users[person.user_id]
    assert current.profile.id == ROOT_PROFILE.key
    assert current.access_keys == initial.access_keys
    assert current.operational == initial.operational


def test_disables_missing_memberships_without_deleting_users():
    person = identity('user-3')
    initial = runtime_user(person)
    runtime = Runtime((initial,))
    service = workflow((person,), Memberships(()), runtime)

    preview = service.inspect()
    assert preview.disable_ids == (person.user_id,)
    service.apply(preview)

    assert runtime.users[person.user_id].enabled is False
    assert runtime.users[person.user_id].access_keys == initial.access_keys
    assert runtime.users[person.user_id].operational == initial.operational
    assert service.inspect().has_changes is False


def test_reconstruction_does_not_disable_guest_or_local_runtime():
    guests = (runtime_user(identity('guest'), profile=GUEST_PROFILE),)
    locals_ = (runtime_user(identity('local'), profile=LOCAL_PROFILE),)
    runtime = Runtime((*guests, *locals_))
    service = workflow((), Memberships(()), runtime)

    assert service.inspect().has_changes is False
    service.apply(service.inspect())
    assert runtime.published == []


def test_rejects_stale_preview_before_publishing():
    person = identity('user-4')
    memberships = Memberships((membership(person),))
    runtime = Runtime()
    service = workflow((person,), memberships, runtime)
    preview = service.inspect()
    memberships.memberships = (membership(person, 'root'),)

    with pytest.raises(UsersReconstructionConflictError, match='preview changed'):
        service.apply(preview)
    assert runtime.published == []


def test_rejects_membership_without_durable_identity():
    person = identity('missing')
    service = workflow((), Memberships((membership(person),)), Runtime())

    with pytest.raises(UsersReconstructionConflictError, match='durable user identity'):
        service.inspect()
