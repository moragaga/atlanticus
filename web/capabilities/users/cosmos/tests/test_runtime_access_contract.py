from dataclasses import replace
from unittest.mock import Mock

import pytest

from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import BASIC_PROFILE
from atlanticus.web.users.cosmos import CosmosUsersRuntimeStore
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity


def _runtime_user() -> RuntimeUser:
    issuer = 'issuer'
    subject_id = 'subject'
    return RuntimeUser(
        identity=UserIdentity(
            user_id=build_user_key(issuer=issuer, subject_id=subject_id),
            issuer=issuer,
            subject_id=subject_id,
            display_name='User',
        ),
        enabled=True,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE),
    )


def _identity() -> AuthenticatedIdentity:
    return AuthenticatedIdentity(provider_key='entra', issuer='issuer', subject_id='subject')


def _store() -> tuple[CosmosUsersRuntimeStore, dict[str, dict[str, object]]]:
    documents: dict[str, dict[str, object]] = {}
    client = Mock()
    client.query_items.side_effect = lambda **_kwargs: tuple(documents.values())
    client.find_item.side_effect = lambda **kwargs: documents.get(kwargs['item_id'])

    def create_item(*, container_name, item):
        del container_name
        saved = dict(item, _etag='fixture-etag')
        documents[item['id']] = saved
        return saved

    client.create_item.side_effect = create_item
    client.patch_item.side_effect = AssertionError('Unexpected Cosmos patch')
    client.delete_item.side_effect = AssertionError('Unexpected Cosmos delete')
    return CosmosUsersRuntimeStore(client=client, container_name='users-runtime'), documents


def test_cosmos_v2_persists_and_reads_all_resolved_access_keys():
    store, documents = _store()
    user = replace(_runtime_user(), access_keys=('dashboard.view', 'reports.read'))

    assert store.replace_all((user,)) == (user,)
    document = documents[user.user_id]
    assert document['schema_version'] == 2
    assert document['user']['access_keys'] == ['dashboard.view', 'reports.read']
    assert store.resolve(_identity()) == user
    assert store.list_users() == (user,)


@pytest.mark.parametrize('invalid', ['v1', 'missing_grants'])
def test_cosmos_rejects_older_or_incomplete_documents(invalid):
    store, documents = _store()
    user = _runtime_user()
    store.replace_all((user,))
    document = documents[user.user_id]
    if invalid == 'v1':
        document['schema_version'] = 1
    else:
        del document['user']['access_keys']

    with pytest.raises(UsersDefinitionError):
        store.resolve(_identity())
