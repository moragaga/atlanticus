from typing import Any

from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationLinkConfiguration,
)
from atlanticus.web.navigation.configuration.adapters import (
    CosmosNavigationProjectionRepository,
    CosmosNavigationProjectionSettings,
)
from atlanticus.web.navigation.configuration.projection import NavigationConfigurationProjection


class FakeCosmosClient:
    def __init__(self) -> None:
        self.document: dict[str, Any] | None = None

    def health_check(self) -> bool:
        return True

    def find_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
    ) -> dict[str, Any] | None:
        assert container_name == 'configuration'
        assert item_id == 'navigation'
        assert partition_key == 'navigation'
        return self.document

    def upsert_item(
        self,
        *,
        container_name: str,
        item: dict[str, Any],
    ) -> dict[str, Any]:
        assert container_name == 'configuration'
        self.document = item
        return item


def test_cosmos_projection_round_trip() -> None:
    client = FakeCosmosClient()
    repository = CosmosNavigationProjectionRepository(
        client=client,
        settings=CosmosNavigationProjectionSettings(container_name='configuration'),
    )
    projection = NavigationConfigurationProjection.create(
        source_revision='source-revision',
        projected_by='administrator',
        catalog=NavigationConfigurationCatalog(
            links=(NavigationLinkConfiguration(key='home', label='Home', href='/'),),
        ),
    )

    assert repository.load() is None
    repository.save(projection)

    loaded = repository.load()
    assert loaded.revision == projection.revision
    assert loaded.definition.home_route_key is None
    assert repository.health_check() is True
