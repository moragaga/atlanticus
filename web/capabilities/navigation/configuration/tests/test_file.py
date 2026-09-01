from pathlib import Path

from atlanticus.web.navigation.configuration import (
    NavigationConfigurationBundle,
    NavigationConfigurationCatalog,
    NavigationLinkConfiguration,
)
from atlanticus.web.navigation.configuration.adapters import (
    FileNavigationConfigurationSettings,
    FileNavigationConfigurationStore,
    FileNavigationProjectionRepository,
    FileNavigationProjectionSettings,
)
from atlanticus.web.navigation.configuration.projection import NavigationConfigurationProjection


def _catalog() -> NavigationConfigurationCatalog:
    return NavigationConfigurationCatalog(
        links=(NavigationLinkConfiguration(key='home', label='Home', href='/'),),
    )


def test_file_source_and_projection_are_independent(tmp_path: Path) -> None:
    source = FileNavigationConfigurationStore(
        FileNavigationConfigurationSettings(root=tmp_path / 'source')
    )
    projection = FileNavigationProjectionRepository(
        FileNavigationProjectionSettings(root=tmp_path / 'projection')
    )
    bundle = NavigationConfigurationBundle.create(
        catalog=_catalog(),
        saved_by='administrator',
    )

    source.publish_bundle(bundle, expected_source_revision=None)

    assert source.fetch_bundle().revision == bundle.revision
    assert projection.load() is None

    projected = NavigationConfigurationProjection.create(
        source_revision=bundle.revision,
        projected_by='administrator',
        catalog=bundle.catalog,
    )
    projection.save(projected)

    assert projection.load().revision == projected.revision
    assert projection.load().definition.find_link('home').href == '/'
    assert source.fetch_bundle().revision == bundle.revision
