from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from atlanticus.web.navigation.configuration.errors import NavigationConfigurationProjectionError
from atlanticus.web.navigation.configuration.projection import NavigationConfigurationProjection


class CosmosClient(Protocol):
    def health_check(self) -> bool: ...

    def find_item(
        self,
        *,
        container_name: str,
        item_id: str,
        partition_key: object,
    ) -> dict[str, Any] | None: ...

    def upsert_item(
        self,
        *,
        container_name: str,
        item: dict[str, Any],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class CosmosNavigationProjectionSettings:
    container_name: str
    item_id: str = 'navigation'
    partition_key: str = 'navigation'

    def __post_init__(self) -> None:
        if not self.container_name.strip():
            raise ValueError('Cosmos navigation configuration container must not be empty')


class CosmosNavigationProjectionRepository:
    def __init__(
        self,
        *,
        client: CosmosClient,
        settings: CosmosNavigationProjectionSettings,
    ) -> None:
        self._client = client
        self._settings = settings

    def load(self) -> NavigationConfigurationProjection | None:
        try:
            document = self._client.find_item(
                container_name=self._settings.container_name,
                item_id=self._settings.item_id,
                partition_key=self._settings.partition_key,
            )
        except Exception as error:
            raise NavigationConfigurationProjectionError(
                'Could not read Cosmos navigation projection'
            ) from error
        if document is None:
            return None
        return NavigationConfigurationProjection.from_document(document)

    def save(
        self,
        projection: NavigationConfigurationProjection,
    ) -> NavigationConfigurationProjection:
        try:
            self._client.upsert_item(
                container_name=self._settings.container_name,
                item=projection.to_document(
                    item_id=self._settings.item_id,
                    partition_key=self._settings.partition_key,
                ),
            )
        except Exception as error:
            raise NavigationConfigurationProjectionError(
                'Could not write Cosmos navigation projection'
            ) from error
        return projection

    def health_check(self) -> bool:
        try:
            return bool(self._client.health_check())
        except Exception:
            return False
