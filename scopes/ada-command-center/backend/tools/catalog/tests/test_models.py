from datetime import UTC, datetime, timedelta

import pytest

from ada.web.tools.enums import ToolConfigurationKind
from ada_command_center.tools.catalog import (
    ToolCatalogEntry,
    ToolCatalogValidationError,
    create_tool_catalog_snapshot,
)
from atlanticus.web.source.models import SourceReleaseId

from .helpers import tool_configuration


def _entry(
    *,
    tool_key: str = 'integrated_operations',
    release_id: str = 'release-1',
) -> ToolCatalogEntry:
    configuration = tool_configuration(tool_key=tool_key, display_name=tool_key)
    assert configuration.structure is not None
    return ToolCatalogEntry(
        tool_key=configuration.tool_key,
        display_name=configuration.display_name,
        kind=configuration.kind,
        source_release_id=SourceReleaseId(release_id),
        structure=configuration.structure,
    )


def test_snapshot_orders_tools_and_supports_lookup() -> None:
    generated_at = datetime(2026, 9, 21, 12, tzinfo=UTC)
    snapshot = create_tool_catalog_snapshot(
        (
            _entry(tool_key='plant'),
            _entry(tool_key='mine'),
        ),
        generated_at_utc=generated_at,
    )

    assert tuple(tool.tool_key for tool in snapshot.tools) == ('mine', 'plant')
    assert snapshot.get('mine') is not None
    assert snapshot.get('unknown') is None


def test_revision_is_independent_from_generation_time() -> None:
    entry = _entry()
    first = create_tool_catalog_snapshot(
        (entry,),
        generated_at_utc=datetime(2026, 9, 21, 12, tzinfo=UTC),
    )
    second = create_tool_catalog_snapshot(
        (entry,),
        generated_at_utc=datetime(2026, 9, 21, 13, tzinfo=UTC),
    )

    assert first.revision == second.revision
    assert first.generated_at_utc != second.generated_at_utc


def test_revision_changes_when_source_release_changes() -> None:
    generated_at = datetime(2026, 9, 21, 12, tzinfo=UTC)
    first = create_tool_catalog_snapshot(
        (_entry(release_id='release-1'),),
        generated_at_utc=generated_at,
    )
    second = create_tool_catalog_snapshot(
        (_entry(release_id='release-2'),),
        generated_at_utc=generated_at + timedelta(minutes=1),
    )

    assert first.revision != second.revision


def test_entry_rejects_structure_from_another_tool() -> None:
    configuration = tool_configuration(tool_key='mine')
    other = tool_configuration(tool_key='plant')
    assert other.structure is not None

    with pytest.raises(
        ToolCatalogValidationError,
        match='structure tool key does not match',
    ):
        ToolCatalogEntry(
            tool_key=configuration.tool_key,
            display_name=configuration.display_name,
            kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
            source_release_id=SourceReleaseId('release-1'),
            structure=other.structure,
        )
