import base64

import pytest

from atlanticus.web.navigation.configuration import (
    NavigationConfigurationBundle,
    NavigationConfigurationCatalog,
    NavigationLinkConfiguration,
)
from atlanticus.web.navigation.configuration.adapters import (
    SharePointNavigationConfigurationSettings,
    SharePointNavigationConfigurationStore,
)
from atlanticus.web.navigation.configuration.errors import NavigationConfigurationSourceError


class FakeSharePointGateway:
    def __init__(self) -> None:
        self.content: str | None = None
        self.reads: list[tuple[str, str]] = []
        self.writes: list[tuple[str, str, str]] = []

    def read(self, *, filename: str, relative_path: str) -> str | None:
        self.reads.append((relative_path, filename))
        return self.content

    def write(self, *, filename: str, relative_path: str, content: str) -> None:
        self.writes.append((relative_path, filename, content))
        self.content = content


def test_sharepoint_store_uses_semantic_read_write_gateway() -> None:
    gateway = FakeSharePointGateway()
    store = SharePointNavigationConfigurationStore(
        gateway=gateway,
        settings=SharePointNavigationConfigurationSettings(),
    )
    bundle = NavigationConfigurationBundle.create(
        catalog=NavigationConfigurationCatalog(
            links=(NavigationLinkConfiguration(key='home', label='Home', href='/'),),
        ),
        saved_by='administrator',
    )

    assert store.fetch_bundle() is None
    store.publish_bundle(bundle, expected_source_revision=None)

    assert store.fetch_bundle().revision == bundle.revision
    assert gateway.reads[-1] == ('navigation', 'navigation_configuration.json.gz')
    assert gateway.writes[0][:2] == ('navigation', 'navigation_configuration.json.gz')
    assert base64.b64decode(gateway.writes[0][2], validate=True)


def test_sharepoint_rejects_stale_expected_revision_before_write() -> None:
    gateway = FakeSharePointGateway()
    store = SharePointNavigationConfigurationStore(
        gateway=gateway,
        settings=SharePointNavigationConfigurationSettings(),
    )
    first = NavigationConfigurationBundle.create(
        catalog=NavigationConfigurationCatalog(
            links=(NavigationLinkConfiguration(key='home', label='Home', href='/'),),
        ),
        saved_by='administrator',
    )
    second = NavigationConfigurationBundle.create(
        catalog=NavigationConfigurationCatalog(
            links=(NavigationLinkConfiguration(key='ops', label='Ops', href='/ops'),),
        ),
        saved_by='second-admin',
    )

    store.publish_bundle(first, expected_source_revision=None)
    writes_before = len(gateway.writes)

    with pytest.raises(NavigationConfigurationSourceError, match='source revision changed'):
        store.publish_bundle(second, expected_source_revision='stale')

    assert len(gateway.writes) == writes_before
    assert store.fetch_bundle().revision == first.revision
