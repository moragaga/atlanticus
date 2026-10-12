from __future__ import annotations

from dataclasses import replace

import pytest

from ada.web.application.generic.users import publication as users_runtime_publication
from ada.web.application.generic.users.publication import AdaCosmosRuntimeUserWriter
from atlanticus.web.profiles.models import BASIC_PROFILE, ROOT_PROFILE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    RuntimeOperational,
    RuntimeOperationalReference,
    RuntimeProfile,
    RuntimeUser,
    UserIdentity,
)
from atlanticus.web.users.store import UsersRuntimeStore


class FakeCosmos:
    def __init__(self):
        self.documents = {}
        self.patches = []

    def find_item(self, *, container_name, item_id, partition_key, include_metadata=False):
        assert container_name == 'users-runtime'
        assert item_id == partition_key
        return self.documents.get(item_id)

    def patch_item(self, *, container_name, item_id, partition_key, operations, if_match_etag):
        doc = self.documents[item_id]
        assert if_match_etag == doc['_etag']
        self.patches.append(tuple(op.path for op in operations))
        for op in operations:
            assert op.operation == 'set'
            doc['user'][op.path.split('/')[-1]] = op.value
        doc['_etag'] = str(int(doc['_etag']) + 1)
        return doc


class FakeRuntime(UsersRuntimeStore):
    def __init__(self, cosmos):
        self.cosmos = cosmos

    def resolve(self, identity):
        key = build_user_key(issuer=identity.issuer, subject_id=identity.subject_id)
        doc = self.cosmos.documents.get(key)
        return None if doc is None else RuntimeUser.from_document(doc['user'])

    def list_users(self):
        return tuple(RuntimeUser.from_document(doc['user']) for doc in self.cosmos.documents.values())

    def upsert_user(self, user):
        self.cosmos.documents[user.user_id] = {
            'id': user.user_id,
            'document_type': 'atlanticus_tool_runtime_user',
            'schema_version': 2,
            'user': user.to_document(),
            '_etag': '1',
        }
        return user

    def replace_all(self, users):
        self.cosmos.documents.clear()
        for user in users:
            self.upsert_user(user)
        return users


def _user():
    issuer = 'urn:atlanticus:ur05c-test'
    subject = 'operator'
    return RuntimeUser(
        identity=UserIdentity(
            user_id=build_user_key(issuer=issuer, subject_id=subject),
            issuer=issuer,
            subject_id=subject,
            display_name='Operator',
        ),
        enabled=True,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE),
        access_keys=('dashboard.view',),
    )


def test_operational_update_patches_only_operational_field(monkeypatch):
    monkeypatch.setattr(users_runtime_publication, 'CosmosClient', FakeCosmos)
    cosmos = FakeCosmos()
    runtime = FakeRuntime(cosmos)
    original = _user()
    runtime.upsert_user(original)
    publisher = AdaCosmosRuntimeUserWriter(
        client=cosmos, store=runtime, container_name='users-runtime'
    )
    operational = RuntimeOperational(
        position=RuntimeOperationalReference(id='operator', label='Operator')
    )
    updated = publisher.upsert_operational(original.user_id, operational)
    assert updated.identity == original.identity
    assert updated.enabled == original.enabled
    assert updated.profile == original.profile
    assert updated.access_keys == original.access_keys
    assert updated.operational == operational
    assert cosmos.patches == [('/user/operational',)]


def test_base_update_preserves_operational_enrichment(monkeypatch):
    monkeypatch.setattr(users_runtime_publication, 'CosmosClient', FakeCosmos)
    cosmos = FakeCosmos()
    runtime = FakeRuntime(cosmos)
    original = _user()
    operational = RuntimeOperational(area=RuntimeOperationalReference(id='mina', label='Mina'))
    runtime.upsert_user(replace(original, operational=operational))
    publisher = AdaCosmosRuntimeUserWriter(
        client=cosmos, store=runtime, container_name='users-runtime'
    )
    revised = replace(original, enabled=False, profile=RuntimeProfile.from_profile(ROOT_PROFILE), access_keys=())
    updated = publisher.upsert_base_user(revised)
    assert updated.operational == operational
    assert updated.access_keys == original.access_keys
    assert updated.profile == revised.profile
    assert not updated.enabled
    assert cosmos.patches == [
        ('/user/identity', '/user/enabled', '/user/profile')
    ]


def test_operational_publication_rejects_missing_runtime_user(monkeypatch):
    monkeypatch.setattr(users_runtime_publication, 'CosmosClient', FakeCosmos)
    cosmos = FakeCosmos()
    publisher = AdaCosmosRuntimeUserWriter(
        client=cosmos, store=FakeRuntime(cosmos), container_name='users-runtime'
    )
    with pytest.raises(ValueError, match='must exist'):
        publisher.upsert_operational(_user().user_id, RuntimeOperational())


def test_base_publication_does_not_need_operational_or_access(monkeypatch, tmp_path):
    from dataclasses import replace as dataclass_replace

    from ada.web.application.configuration_manager.local_runtime import (
        create_local_configuration_manager_stores,
    )
    from ada.web.application.generic.users.materialization import AdaUsersRuntimeMaterializer
    from ada.web.application.generic.users.publication import AdaLocalRuntimeUserWriter
    from atlanticus.web.users.models import ToolUserMembership

    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'source')
    stores = dataclass_replace(stores, operational_source=None, operational=None)
    user = _user()
    stores.users_registry.replace((user.identity,), expected_version=None)
    stores.users_memberships.replace(
        (ToolUserMembership(user_id=user.user_id, profile_key='basic'),),
        expected_version=None,
    )
    publisher = AdaUsersRuntimeMaterializer(stores=stores)
    persisted = publisher.publish_user(
        user.user_id, writer=AdaLocalRuntimeUserWriter(stores.users_runtime)
    )
    assert persisted.enabled
    assert persisted.profile.id == 'basic'
    assert persisted.operational == RuntimeOperational()
    assert persisted.access_keys == ()
