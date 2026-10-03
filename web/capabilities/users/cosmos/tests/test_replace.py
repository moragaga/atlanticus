from atlanticus.connectivity.cosmos import CosmosConflictError, CosmosItemNotFoundError


class MemoryCosmos:
    def __init__(self):
        self.items = {}
        self.revision = 0

    def _with_etag(self, document):
        result = dict(document)
        result['_etag'] = f'e{self.revision}'
        return result

    def find_item(
        self,
        *,
        container_name,
        item_id,
        partition_key,
        include_metadata=False,
    ):
        value = self.items.get(item_id)
        return None if value is None else dict(value)

    def create_item(self, *, container_name, item, include_metadata=False):
        item_id = item['id']
        if item_id in self.items:
            raise CosmosConflictError(item_id)
        self.revision += 1
        self.items[item_id] = self._with_etag(item)
        return dict(self.items[item_id])

    def patch_item(
        self,
        *,
        container_name,
        item_id,
        partition_key,
        operations,
        if_match_etag=None,
        include_metadata=False,
    ):
        if item_id not in self.items:
            raise CosmosItemNotFoundError(item_id)
        current = self.items[item_id]
        if if_match_etag is not None and current.get('_etag') != if_match_etag:
            raise CosmosConflictError(item_id)
        updated = dict(current)
        for operation in operations:
            assert operation.operation == 'set'
            updated[operation.path.removeprefix('/')] = operation.value
        self.revision += 1
        updated['_etag'] = f'e{self.revision}'
        self.items[item_id] = updated
        return dict(updated)

    def query_items(
        self,
        *,
        container_name,
        query,
        parameters=None,
        cross_partition=False,
        include_metadata=False,
    ):
        values = {}
        for parameter in parameters or ():
            values[parameter.name] = parameter.value
        result = []
        for item in self.items.values():
            if (
                item.get('document_type') == values.get('@document_type')
            ):
                result.append(dict(item))
        return tuple(result)

    def delete_item(
        self,
        *,
        container_name,
        item_id,
        partition_key,
        if_match_etag=None,
    ):
        if item_id not in self.items:
            raise CosmosItemNotFoundError(item_id)
        current = self.items[item_id]
        if if_match_etag is not None and current.get('_etag') != if_match_etag:
            raise CosmosConflictError(item_id)
        del self.items[item_id]

from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.profiles.models import BASIC_PROFILE, ROOT_PROFILE
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeProfile, RuntimeUser, UserIdentity


def identity(subject='subject'):
    return AuthenticatedIdentity(
        provider_key='entra',
        issuer='issuer',
        subject_id=subject,
    )


def runtime_user(subject='subject', *, root=False):
    user_identity = UserIdentity(
        user_id=build_user_key(issuer='issuer', subject_id=subject),
        issuer='issuer',
        subject_id=subject,
        display_name=f'User {subject}',
    )
    return RuntimeUser(
        identity=user_identity,
        enabled=True,
        profile=RuntimeProfile.from_profile(ROOT_PROFILE if root else BASIC_PROFILE),
    )

from atlanticus.web.users.cosmos import CosmosUsersRuntimeStore


def test_replace_all_creates_updates_and_deletes_until_runtime_matches():
    cosmos = MemoryCosmos()
    store = CosmosUsersRuntimeStore(
        client=cosmos,
        container_name='users-runtime',
    )
    original = (runtime_user('a'), runtime_user('obsolete'))
    assert store.replace_all(original) == tuple(sorted(original, key=lambda user: user.user_id))
    desired = (runtime_user('a', root=True), runtime_user('b'))
    persisted = store.replace_all(desired)
    assert persisted == tuple(sorted(desired, key=lambda user: user.user_id))
    assert store.list_users() == persisted
    assert store.resolve(identity('obsolete')) is None


def test_replace_all_is_idempotent_for_same_runtime_snapshot():
    cosmos = MemoryCosmos()
    store = CosmosUsersRuntimeStore(
        client=cosmos,
        container_name='users-runtime',
    )
    desired = (runtime_user('a'),)
    first = store.replace_all(desired)
    second = store.replace_all(desired)
    assert first == second == desired
