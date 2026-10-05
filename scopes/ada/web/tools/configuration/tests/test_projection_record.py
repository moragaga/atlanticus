from datetime import UTC, datetime

import pytest

from ada.web.tools.configuration import ToolConfiguration
from ada.web.tools.configuration.errors import ToolConfigurationProjectionError
from ada.web.tools.configuration.projection_record import (
    tool_projection_from_document,
    tool_projection_to_document,
)
from atlanticus.web.projection.models import ProjectionRecord, ProjectionTarget
from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef


def _configuration() -> ToolConfiguration:
    return ToolConfiguration.from_document(
        {
            'tool_key': 'operaciones_integradas',
            'display_name': 'Operaciones Integradas',
            'kind': 'process',
            'source_consumption': {
                'tool_key': 'operaciones_integradas',
                'source_keys': ['pi'],
            },
            'source_operational_participation': {
                'tool_key': 'operaciones_integradas',
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
                'tool_key': 'operaciones_integradas',
                'kind': 'process',
                'operational_scope': 'mine',
                'center_component_key': 'center',
                'components': [
                    {
                        'key': 'center',
                        'display_name': 'Centro',
                        'subcomponents': [
                            {
                                'key': 'primary',
                                'display_name': 'Principal',
                                'linked_component_keys': [],
                            }
                        ],
                    }
                ],
            },
        }
    )


def _record(configuration: ToolConfiguration | None = None) -> ProjectionRecord[ToolConfiguration]:
    published = datetime(2026, 9, 20, 20, tzinfo=UTC)
    dependency = ProjectionTarget(
        source_key=SourceKey('profiles'),
        source_release=SourceReleaseRef(
            release_id=SourceReleaseId('profiles-release'),
            published_at_utc=published,
        ),
    )
    return ProjectionRecord(
        source_key=SourceKey('tools'),
        source_release_id=SourceReleaseId('tools-release'),
        source_published_at_utc=published,
        projected_at_utc=datetime(2026, 9, 20, 20, 0, 1, tzinfo=UTC),
        payload=configuration or _configuration(),
        dependencies=(dependency,),
    )


def _integrated_configuration() -> ToolConfiguration:
    document = _configuration().to_document()
    document['kind'] = 'integrated_operations'
    document['structure'] = {
        'tool_key': 'operaciones_integradas',
        'kind': 'integrated_operations',
        'components': [
            {
                'key': 'extraction',
                'display_name': 'Extracción',
                'scope': 'mine',
                'subcomponents': [
                    {
                        'key': 'mine_detail',
                        'display_name': 'Detalle Mina',
                        'linked_component_keys': [],
                    }
                ],
            },
            {
                'key': 'concentrator',
                'display_name': 'Concentradora',
                'scope': 'plant',
                'subcomponents': [
                    {
                        'key': 'plant_detail',
                        'display_name': 'Detalle Planta',
                        'linked_component_keys': [],
                    }
                ],
            },
        ],
    }
    return ToolConfiguration.from_document(document)


def test_tool_projection_document_round_trips_exact_contract() -> None:
    record = _record()

    document = tool_projection_to_document(
        record,
        item_id='tool-projection-item',
        partition_key='conciencia_situacional/operaciones_integradas',
    )
    restored = tool_projection_from_document(document)

    assert document['id'] == 'tool-projection-item'
    assert document['partition_key'] == 'conciencia_situacional/operaciones_integradas'
    assert restored == record


def test_tool_projection_preserves_integrated_operational_component_order() -> None:
    record = _record(_integrated_configuration())

    document = tool_projection_to_document(record)
    restored = tool_projection_from_document(document)

    assert [
        component['key'] for component in document['payload']['structure']['components']
    ] == ['extraction', 'concentrator']
    assert tuple(
        component.key for component in restored.payload.structure.components
    ) == ('extraction', 'concentrator')


def test_tool_projection_document_rejects_wrong_document_type() -> None:
    document = tool_projection_to_document(_record())
    document['document_type'] = 'wrong'

    with pytest.raises(
        ToolConfigurationProjectionError,
        match='document type',
    ):
        tool_projection_from_document(document)
