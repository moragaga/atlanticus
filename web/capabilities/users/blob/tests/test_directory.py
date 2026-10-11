from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.users.administration import UserCandidateState, UsersAdministrationService
from atlanticus.web.users.blob.directory import BlobUsersDirectoryReader
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.models import DiscoveredUser, ToolMembershipSnapshot, ToolUserMembership, UsersRegistrySnapshot


class Storage:
    def __init__(self, documents=()):
        self.documents = dict(documents)
        self.calls = []

    def list_blobs(self, *, container_name, prefix=None, max_items=None):
        self.calls.append((container_name, prefix, max_items))
        return tuple(
            SimpleNamespace(name=name, size=len(payload))
            for name, payload in self.documents.items() if name.startswith(prefix)
        )

    def download(self, *, container_name, blob_name):
        return self.documents[blob_name]


def document(issuer='issuer', subject='user-one', display_name='One', email=None):
    return json.dumps({
        'document_type': 'atlanticus_discovered_user',
        'schema_version': 1,
        'issuer': issuer,
        'subject_id': subject,
        'display_name': display_name,
        'email': email,
    }).encode()


def reader(*payloads):
    prefix = 'ada/users/discovery'
    docs = {}
    for raw in payloads:
        d = json.loads(raw)
        name = DiscoveredUser(issuer=d['issuer'], subject_id=d['subject_id']).user_id
        docs[f'{prefix}/{name}.json'] = raw
    storage = Storage(docs)
    return BlobUsersDirectoryReader(client=storage, container_name='qual', prefix=prefix), storage


def test_directory_is_lazy_and_canonical():
    directory, storage = reader(document(), document(subject='user-two', display_name='Two'))
    assert storage.calls == []
    users = directory.list_discovered()
    assert len(users) == 2
    assert {user.subject_id for user in users} == {'user-one', 'user-two'}
    assert storage.calls == [('qual', 'ada/users/discovery/', 200)]


def test_identity_collisions_are_not_derived_from_names():
    directory, _ = reader(document(subject='one', display_name='Same'), document(subject='two', display_name='Same'))
    users = directory.list_discovered()
    assert len({user.user_id for user in users}) == 2


def test_wrong_name_fails_closed():
    storage = Storage({'ada/users/discovery/wrong.json': document()})
    directory = BlobUsersDirectoryReader(client=storage, container_name='qual', prefix='ada/users/discovery')
    with pytest.raises(UsersDefinitionError, match='filename'):
        directory.list_discovered()


def test_invalid_document_fails_closed():
    user = DiscoveredUser(issuer='issuer', subject_id='one')
    storage = Storage({f'ada/users/discovery/{user.user_id}.json': b'not-json'})
    directory = BlobUsersDirectoryReader(client=storage, container_name='qual', prefix='ada/users/discovery')
    with pytest.raises(UsersDefinitionError, match='invalid'):
        directory.list_discovered()


def test_oversized_document_fails_closed():
    user = DiscoveredUser(issuer='issuer', subject_id='one')
    storage = Storage({f'ada/users/discovery/{user.user_id}.json': b'x' * 16385})
    directory = BlobUsersDirectoryReader(client=storage, container_name='qual', prefix='ada/users/discovery')
    with pytest.raises(UsersDefinitionError, match='size limit'):
        directory.list_discovered()


def test_global_user_and_directory_user_remain_distinct_or_merge_canonically():
    directory, _ = reader(document(subject='registered'), document(subject='new', display_name='New'))
    registered = DiscoveredUser(issuer='issuer', subject_id='registered', display_name='One').to_identity()

    class Registry:
        def load(self):
            return UsersRegistrySnapshot(users=(registered,), version='v1')

    class Memberships:
        def load(self):
            return ToolMembershipSnapshot(version='m1')

    candidates = UsersAdministrationService(
        registry=Registry(), memberships=Memberships(), directory=directory,
        profiles=lambda: ProfileCatalog(),
    ).discover().candidates
    assert len(candidates) == 2
    assert {candidate.state for candidate in candidates} == {UserCandidateState.PROMOTABLE}


def test_promoted_candidate_does_not_reenter_promotion_queue():
    directory, _ = reader(document(subject='promoted'))
    user = directory.list_discovered()[0].to_identity()

    class Registry:
        def load(self):
            return UsersRegistrySnapshot(users=(user,), version='v1')

    class Memberships:
        def load(self):
            return ToolMembershipSnapshot(memberships=(ToolUserMembership(user_id=user.user_id, profile_key='basic'),), version='m1')

    candidates = UsersAdministrationService(
        registry=Registry(), memberships=Memberships(), directory=directory,
        profiles=lambda: ProfileCatalog(),
    ).discover().candidates
    assert len(candidates) == 1
    assert candidates[0].state is UserCandidateState.PROMOTED
