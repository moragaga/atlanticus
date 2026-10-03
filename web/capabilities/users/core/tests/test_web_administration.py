from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.users.administration import UsersAdministrationService
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    ToolMembershipSnapshot,
    ToolUserMembership,
    UserIdentity,
    UsersRegistrySnapshot,
)
from atlanticus.web.users.store import ToolMembershipStore, UsersRegistryStore
from atlanticus.web.users.web.serialization import snapshot_to_document


class Registry(UsersRegistryStore):
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def load(self):
        return self.snapshot

    def replace(self, users, *, expected_version):
        raise AssertionError


class Memberships(ToolMembershipStore):
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def load(self):
        return self.snapshot

    def replace(self, memberships, *, expected_version):
        raise AssertionError


def test_administration_serialization_exposes_identity_and_membership_versions():
    identity = UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id='subject'),
        issuer='issuer',
        subject_id='subject',
        display_name='User',
    )
    membership = ToolUserMembership(user_id=identity.user_id, profile_key='root')
    service = UsersAdministrationService(
        registry=Registry(UsersRegistrySnapshot((identity,), 'r1')),
        memberships=Memberships(ToolMembershipSnapshot((membership,), 'm1')),
        profiles=lambda: ProfileCatalog(),
    )
    document = snapshot_to_document(service.discover())
    assert document['registry_version'] == 'r1'
    assert document['membership_version'] == 'm1'
    candidate = document['candidates'][0]
    assert candidate['promoted_user']['profile_key'] == 'root'
    assert 'avatar_background_color' not in candidate['promoted_user']
