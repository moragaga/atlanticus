from datetime import UTC, datetime

import pytest

from ada.web.tools.configuration import (
    ToolConfigurationProjectionError,
    ToolProjectionBuilder,
    ToolSourceCodec,
)
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.source.models import (
    Digest,
    SourceKey,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
)

from .helpers import configuration_without_structure, valid_configuration


def _release() -> SourceReleaseMetadata:
    source_key = SourceKey('ada-tool-configuration')
    return SourceReleaseMetadata(
        schema_version=1,
        source_key=source_key,
        release_ref=SourceReleaseRef(
            release_id=SourceReleaseId('release-1'),
            published_at_utc=datetime(2026, 9, 16, 12, 0, tzinfo=UTC),
        ),
        content_hash=Digest('sha256', 'abc'),
        resources=(),
    )


def test_projection_builder_builds_tool_configuration_from_source_release() -> None:
    release = _release()
    configuration = valid_configuration()
    resources = (
        ToolSourceCodec().encode(configuration=configuration, published_by='manager-user'),
    )
    target = ProjectionTarget(
        source_key=release.source_key,
        source_release=release.release_ref,
    )

    projected = ToolProjectionBuilder().build(
        target=target,
        release=release,
        resources=resources,
    )

    assert projected == configuration


def test_projection_builder_rejects_non_operational_tool_configuration() -> None:
    release = _release()
    resources = (
        ToolSourceCodec().encode(
            configuration=configuration_without_structure(),
            published_by='manager-user',
        ),
    )
    target = ProjectionTarget(
        source_key=release.source_key,
        source_release=release.release_ref,
    )

    with pytest.raises(
        ToolConfigurationProjectionError,
        match='Published Tool Configuration is not valid for projection',
    ):
        ToolProjectionBuilder().build(
            target=target,
            release=release,
            resources=resources,
        )
