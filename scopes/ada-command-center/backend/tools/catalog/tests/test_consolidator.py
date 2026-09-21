from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ada.web.tools.configuration import ToolConfiguration
from ada_command_center.tools.catalog import (
    ToolCatalogConsolidationError,
    ToolCatalogConsolidator,
    ToolCatalogInput,
    ToolCatalogSnapshot,
    ToolCatalogStore,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import SourceKey

from .helpers import tool_projection


class ProjectionStoreStub(ProjectionStore[ToolConfiguration]):
    def __init__(self, active: ProjectionRecord[ToolConfiguration] | None) -> None:
        self.active = active
        self.requests: list[SourceKey] = []

    def get_active(self, source_key: SourceKey) -> ProjectionRecord[ToolConfiguration] | None:
        self.requests.append(source_key)
        return self.active

    def replace_active(
        self,
        projection: ProjectionRecord[ToolConfiguration],
    ) -> ProjectionRecord[ToolConfiguration]:
        self.active = projection
        return projection


class FailingProjectionStore(ProjectionStore[ToolConfiguration]):
    def get_active(self, source_key: SourceKey) -> ProjectionRecord[ToolConfiguration] | None:
        del source_key
        raise RuntimeError('boom')

    def replace_active(
        self,
        projection: ProjectionRecord[ToolConfiguration],
    ) -> ProjectionRecord[ToolConfiguration]:
        return projection


class CatalogStoreStub(ToolCatalogStore):
    def __init__(self) -> None:
        self.current: ToolCatalogSnapshot | None = None
        self.replacements = 0

    def get_current(self) -> ToolCatalogSnapshot | None:
        return self.current

    def replace_current(self, snapshot: ToolCatalogSnapshot) -> ToolCatalogSnapshot:
        self.current = snapshot
        self.replacements += 1
        return snapshot


def test_refresh_consolidates_all_tools_and_publishes_once() -> None:
    mine = ProjectionStoreStub(tool_projection(tool_key='mine', display_name='Mina'))
    plant = ProjectionStoreStub(
        tool_projection(
            tool_key='plant',
            display_name='Planta',
            release_id='release-2',
            component_key='plant',
        )
    )
    store = CatalogStoreStub()
    consolidator = ToolCatalogConsolidator(
        inputs=(
            ToolCatalogInput(input_key='mine-app', projection=mine),
            ToolCatalogInput(input_key='plant-app', projection=plant),
        ),
        store=store,
        clock=lambda: datetime(2026, 9, 21, 12, tzinfo=UTC),
    )

    snapshot = consolidator.refresh()

    assert store.current == snapshot
    assert store.replacements == 1
    assert tuple(tool.tool_key for tool in snapshot.tools) == ('mine', 'plant')
    assert snapshot.get('plant').source_release_id.value == 'release-2'
    assert mine.requests == [SourceKey('tools')]
    assert plant.requests == [SourceKey('tools')]


def test_missing_input_does_not_publish_partial_catalog() -> None:
    store = CatalogStoreStub()
    consolidator = ToolCatalogConsolidator(
        inputs=(
            ToolCatalogInput(
                input_key='mine-app',
                projection=ProjectionStoreStub(tool_projection(tool_key='mine')),
            ),
            ToolCatalogInput(
                input_key='plant-app',
                projection=ProjectionStoreStub(None),
            ),
        ),
        store=store,
    )

    with pytest.raises(ToolCatalogConsolidationError, match='no active projection'):
        consolidator.refresh()

    assert store.current is None
    assert store.replacements == 0


def test_unavailable_input_does_not_publish_partial_catalog() -> None:
    store = CatalogStoreStub()
    consolidator = ToolCatalogConsolidator(
        inputs=(ToolCatalogInput(input_key='mine-app', projection=FailingProjectionStore()),),
        store=store,
    )

    with pytest.raises(ToolCatalogConsolidationError, match='Could not read'):
        consolidator.refresh()

    assert store.replacements == 0


def test_duplicate_tool_key_is_rejected_without_publication() -> None:
    store = CatalogStoreStub()
    consolidator = ToolCatalogConsolidator(
        inputs=(
            ToolCatalogInput(
                input_key='first',
                projection=ProjectionStoreStub(tool_projection(tool_key='mine')),
            ),
            ToolCatalogInput(
                input_key='second',
                projection=ProjectionStoreStub(
                    tool_projection(tool_key='mine', release_id='release-2')
                ),
            ),
        ),
        store=store,
    )

    with pytest.raises(ToolCatalogConsolidationError, match='duplicate tool_key'):
        consolidator.refresh()

    assert store.replacements == 0
