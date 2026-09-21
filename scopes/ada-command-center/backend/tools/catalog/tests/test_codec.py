from datetime import UTC, datetime

import pytest

from ada_command_center.tools.catalog import (
    ToolCatalogCodecError,
    ToolCatalogEntry,
    create_tool_catalog_snapshot,
    tool_catalog_from_bytes,
    tool_catalog_to_bytes,
)
from atlanticus.web.source.models import SourceReleaseId

from .helpers import tool_configuration


def _snapshot():
    configuration = tool_configuration()
    assert configuration.structure is not None
    return create_tool_catalog_snapshot(
        (
            ToolCatalogEntry(
                tool_key=configuration.tool_key,
                display_name=configuration.display_name,
                kind=configuration.kind,
                source_release_id=SourceReleaseId('release-1'),
                structure=configuration.structure,
            ),
        ),
        generated_at_utc=datetime(2026, 9, 21, 12, tzinfo=UTC),
    )


def test_codec_round_trips_catalog() -> None:
    snapshot = _snapshot()

    restored = tool_catalog_from_bytes(tool_catalog_to_bytes(snapshot))

    assert restored == snapshot


def test_codec_rejects_modified_revision() -> None:
    payload = tool_catalog_to_bytes(_snapshot()).replace(
        b'"revision":"',
        b'"revision":"invalid-',
        1,
    )

    with pytest.raises(ToolCatalogCodecError, match='document contract'):
        tool_catalog_from_bytes(payload)
