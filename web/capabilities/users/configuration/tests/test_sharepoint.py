import base64

import pytest

from atlanticus.web.users.configuration import UsersConfigurationBundle, UsersConfigurationCatalog
from atlanticus.web.users.configuration.adapters import (
    SharePointUsersConfigurationSettings,
    SharePointUsersConfigurationStore,
)
from atlanticus.web.users.configuration.errors import UsersConfigurationSourceError


class FakeSharePointGateway:
    def __init__(self) -> None:
        self.files: dict[tuple[str, str], str] = {}
        self.reads: list[tuple[str, str]] = []
        self.writes: list[tuple[str, str, str]] = []

    def read(self, *, filename: str, relative_path: str) -> str | None:
        self.reads.append((relative_path, filename))
        return self.files.get((relative_path, filename))

    def write(self, *, filename: str, relative_path: str, content: str) -> None:
        self.writes.append((relative_path, filename, content))
        self.files[(relative_path, filename)] = content


def test_sharepoint_store_uses_semantic_read_write_gateway() -> None:
    gateway = FakeSharePointGateway()
    store = SharePointUsersConfigurationStore(
        gateway=gateway,
        settings=SharePointUsersConfigurationSettings(),
    )
    bundle = UsersConfigurationBundle.create(
        catalog=UsersConfigurationCatalog(
            administrator_background_color='#673AB7',
            guest_background_color='#FF5722',
        ),
        saved_by='administrator',
    )

    store.publish_bundle(bundle, expected_source_revision=None)
    loaded = store.fetch_bundle()

    assert loaded.revision == bundle.revision
    assert base64.b64decode(gateway.writes[0][2])[:2] == b'\x1f\x8b'
    assert set(gateway.reads) == {('users', 'users_configuration.json.gz')}
    assert {(path, filename) for path, filename, _ in gateway.writes} == {
        ('users', 'users_configuration.json.gz')
    }


def test_sharepoint_rejects_stale_expected_revision_before_write() -> None:
    gateway = FakeSharePointGateway()
    store = SharePointUsersConfigurationStore(
        gateway=gateway,
        settings=SharePointUsersConfigurationSettings(),
    )
    first = UsersConfigurationBundle.create(
        catalog=UsersConfigurationCatalog(
            administrator_background_color='#673AB7',
            guest_background_color='#FF5722',
        ),
        saved_by='administrator',
    )
    second = UsersConfigurationBundle.create(
        catalog=UsersConfigurationCatalog(
            administrator_background_color='#112233',
            guest_background_color='#445566',
        ),
        saved_by='second-admin',
    )

    store.publish_bundle(first, expected_source_revision=None)
    writes_before = len(gateway.writes)

    with pytest.raises(UsersConfigurationSourceError, match='source revision changed'):
        store.publish_bundle(second, expected_source_revision='stale')

    assert len(gateway.writes) == writes_before
    assert store.fetch_bundle().revision == first.revision
