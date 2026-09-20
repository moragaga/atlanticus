from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.users.administration import UsersAdministrationService
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import UserRecord, UsersRegistrySnapshot
from atlanticus.web.users.store import UsersAdministrationStore, UsersRegistryStore
from atlanticus.web.users.web.layout import render_managed_rows, render_promotion_rows
from atlanticus.web.users.web.serialization import preserve_profiles, snapshot_to_document


class Registry(UsersRegistryStore):
    def __init__(self, users):
        self.snapshot = UsersRegistrySnapshot(users=tuple(users), version='v1')

    def load(self):
        return self.snapshot

    def replace(self, users, *, expected_version):
        self.snapshot = UsersRegistrySnapshot(users=tuple(users), version='v2')
        return self.snapshot


class Promoted(UsersAdministrationStore):
    def __init__(self, users=()):
        self.users = {user.user_id: user for user in users}

    def get(self, user_id):
        return self.users.get(user_id)

    def list_users(self):
        return tuple(self.users.values())

    def create(self, user):
        self.users[user.user_id] = user
        return user

    def replace(self, user):
        self.users[user.user_id] = user
        return user


def _user(index: int, *, enabled: bool = True) -> UserRecord:
    subject = f'user-{index}'
    return UserRecord(
        user_id=build_user_key(issuer='entra', subject_id=subject),
        issuer='entra',
        subject_id=subject,
        display_name=f'User {index:02d}',
        email=f'user{index:02d}@example.com',
        enabled=enabled,
        profile_key='basic',
    )


def test_users_ui_reuses_shared_10_20_pagination_contract() -> None:
    users = tuple(_user(index) for index in range(1, 22))
    document = snapshot_to_document(
        UsersAdministrationService(
            registry=Registry(users),
            promoted=Promoted(),
            profiles=ProfileCatalog,
        ).discover()
    )

    _rows, page = render_promotion_rows(
        document,
        query=None,
        state_filter='all',
        page_number=2,
        page_size=10,
        can_manage=True,
    )

    assert page.start_index == 11
    assert page.end_index == 20
    assert page.total_count == 21


def test_managed_filters_use_profile_and_enabled_state() -> None:
    active = _user(1, enabled=True)
    disabled = _user(2, enabled=False)
    document = snapshot_to_document(
        UsersAdministrationService(
            registry=Registry((active, disabled)),
            promoted=Promoted((active, disabled)),
            profiles=ProfileCatalog,
        ).discover()
    )

    _rows, page = render_managed_rows(
        document,
        query='user',
        profile_filter='basic',
        enabled_filter='disabled',
        page_number=1,
        page_size=10,
        can_manage=True,
    )

    assert page.total_count == 1


def test_mutation_refresh_preserves_loaded_profiles_snapshot() -> None:
    previous = {'profiles': [{'key': 'basic', 'label': 'Basic'}], 'candidates': []}
    fresh = {'profiles': [{'key': 'new', 'label': 'New'}], 'candidates': [{'user_id': '1'}]}

    preserved = preserve_profiles(fresh, previous)

    assert preserved['profiles'] == previous['profiles']
    assert preserved['candidates'] == fresh['candidates']
