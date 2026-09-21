# Consolidador read-only de Tool Projections nombradas.
# Primero lee y valida todos los inputs; sólo después publica el snapshot completo.
# Si algún input falla o falta, no se invoca el store y por tanto no se publica un parcial.

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from ada.web.tools.configuration import ToolConfiguration
from ada_command_center.tools.catalog.errors import ToolCatalogConsolidationError
from ada_command_center.tools.catalog.models import (
    ToolCatalogEntry,
    ToolCatalogSnapshot,
    create_tool_catalog_snapshot,
)
from ada_command_center.tools.catalog.store import ToolCatalogStore
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey

DEFAULT_TOOL_SOURCE_KEY = SourceKey('tools')


@dataclass(frozen=True, slots=True)
class ToolCatalogInput:
    input_key: str
    projection: ProjectionStore[ToolConfiguration]
    source_key: SourceKey = DEFAULT_TOOL_SOURCE_KEY

    def __post_init__(self) -> None:
        if (
            not isinstance(self.input_key, str)
            or not self.input_key
            or self.input_key != self.input_key.strip()
        ):
            raise ValueError('input_key has an invalid format')
        if not isinstance(self.projection, ProjectionStore):
            raise TypeError('projection must be ProjectionStore')
        if not isinstance(self.source_key, SourceKey):
            raise TypeError('source_key must be SourceKey')


class ToolCatalogConsolidator:
    def __init__(
        self,
        *,
        inputs: tuple[ToolCatalogInput, ...],
        store: ToolCatalogStore,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        normalized_inputs = tuple(inputs)
        if not normalized_inputs:
            raise ValueError('Tool Catalog requires at least one input')
        if any(not isinstance(item, ToolCatalogInput) for item in normalized_inputs):
            raise TypeError('inputs must contain ToolCatalogInput values')
        input_keys = tuple(item.input_key for item in normalized_inputs)
        if len(input_keys) != len(set(input_keys)):
            raise ValueError('Tool Catalog input_key values must be unique')
        if not isinstance(store, ToolCatalogStore):
            raise TypeError('store must be ToolCatalogStore')
        self._inputs = normalized_inputs
        self._store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def refresh(self) -> ToolCatalogSnapshot:
        entries: list[ToolCatalogEntry] = []
        owners: dict[str, str] = {}
        for item in self._inputs:
            try:
                projection = item.projection.get_active(item.source_key)
            except Exception as error:
                raise ToolCatalogConsolidationError(
                    f'Could not read Tool Catalog input: {item.input_key}'
                ) from error
            if projection is None:
                raise ToolCatalogConsolidationError(
                    f'Tool Catalog input has no active projection: {item.input_key}'
                )
            configuration = projection.payload
            if not isinstance(configuration, ToolConfiguration):
                raise ToolCatalogConsolidationError(
                    f'Tool Catalog input has invalid projection payload: {item.input_key}'
                )
            if configuration.structure is None:
                raise ToolCatalogConsolidationError(
                    f'Tool Catalog input has no Tool Structure: {item.input_key}'
                )
            previous_owner = owners.get(configuration.tool_key)
            if previous_owner is not None:
                raise ToolCatalogConsolidationError(
                    f'Tool Catalog contains duplicate tool_key: {configuration.tool_key}'
                )
            owners[configuration.tool_key] = item.input_key
            entries.append(
                ToolCatalogEntry(
                    tool_key=configuration.tool_key,
                    display_name=configuration.display_name,
                    kind=configuration.kind,
                    source_release_id=projection.source_release_id,
                    structure=configuration.structure,
                )
            )
        snapshot = create_tool_catalog_snapshot(
            tuple(entries),
            generated_at_utc=self._clock(),
        )
        return self._store.replace_current(snapshot)
