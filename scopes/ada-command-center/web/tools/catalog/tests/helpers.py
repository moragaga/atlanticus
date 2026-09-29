from __future__ import annotations

from datetime import UTC, datetime

from ada.web.tools.configuration import ToolConfiguration
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId


def tool_configuration(
    *,
    tool_key: str = 'integrated_operations',
    display_name: str = 'Operaciones Integradas',
    component_key: str = 'mine',
) -> ToolConfiguration:
    return ToolConfiguration.from_document(
        {
            'tool_key': tool_key,
            'display_name': display_name,
            'kind': 'integrated_operations',
            'source_consumption': {
                'tool_key': tool_key,
                'source_keys': ['pi'],
            },
            'source_operational_participation': {
                'tool_key': tool_key,
                'control_sources': [
                    {
                        'source_key': 'pi',
                        'pre_degrading_after_seconds': 200,
                        'degrading_after_seconds': 300,
                    }
                ],
                'additional_observation_source_keys': [],
            },
            'structure': {
                'tool_key': tool_key,
                'kind': 'integrated_operations',
                'components': [
                    {
                        'key': component_key,
                        'display_name': component_key.title(),
                        'scope': 'mine',
                        'subcomponents': [
                            {
                                'key': 'primary',
                                'display_name': 'Primario',
                                'linked_component_keys': [],
                            }
                        ],
                    }
                ],
            },
        }
    )


def tool_projection(
    *,
    tool_key: str = 'integrated_operations',
    display_name: str = 'Operaciones Integradas',
    release_id: str = 'release-1',
    component_key: str = 'mine',
) -> ProjectionRecord[ToolConfiguration]:
    timestamp = datetime(2026, 9, 21, 12, tzinfo=UTC)
    return ProjectionRecord(
        source_key=SourceKey('tools'),
        source_release_id=SourceReleaseId(release_id),
        source_published_at_utc=timestamp,
        projected_at_utc=timestamp,
        payload=tool_configuration(
            tool_key=tool_key,
            display_name=display_name,
            component_key=component_key,
        ),
    )
