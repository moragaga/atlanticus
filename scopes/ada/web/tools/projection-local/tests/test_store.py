from datetime import UTC, datetime
from pathlib import Path

from ada.web.storage.namespace import AdaStorageNamespace
from ada.web.tools.configuration import ToolConfiguration
from ada.web.tools.projection.local import (
    LocalToolProjectionStore,
    LocalToolProjectionStoreSettings,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId


def _configuration(tool_key: str) -> ToolConfiguration:
    return ToolConfiguration.from_document(
        {
            'tool_key': tool_key,
            'display_name': tool_key.replace('_', ' ').title(),
            'kind': 'process',
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
                'kind': 'process',
                'operational_scope': 'mine',
                'components': [
                    {
                        'key': 'center',
                        'display_name': 'Centro',
                        'layout_role': 'center',
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


def _record(
    tool_key: str = 'operaciones_integradas',
) -> ProjectionRecord[ToolConfiguration]:
    published = datetime(2026, 9, 20, 20, tzinfo=UTC)
    return ProjectionRecord(
        source_key=SourceKey('tools'),
        source_release_id=SourceReleaseId(f'{tool_key}-release'),
        source_published_at_utc=published,
        projected_at_utc=published,
        payload=_configuration(tool_key),
    )


def test_local_settings_derive_tool_projection_root_from_namespace(
    tmp_path: Path,
) -> None:
    namespace = AdaStorageNamespace(
        application_namespace='conciencia_situacional',
        tool_namespace='operaciones_integradas',
    )

    settings = LocalToolProjectionStoreSettings.from_namespace(
        namespace=namespace,
        base_root=tmp_path,
    )

    assert settings.root == (
        tmp_path / 'conciencia_situacional' / 'operaciones_integradas' / 'projections'
    )


def test_local_tool_projection_survives_restart(tmp_path: Path) -> None:
    settings = LocalToolProjectionStoreSettings.from_namespace(
        namespace=AdaStorageNamespace(
            application_namespace='conciencia_situacional',
            tool_namespace='mina',
        ),
        base_root=tmp_path,
    )
    record = _record('mina')

    first = LocalToolProjectionStore(settings)
    assert first.get_active(record.source_key) is None
    assert first.replace_active(record) == record

    restarted = LocalToolProjectionStore(settings)

    assert restarted.get_active(record.source_key) == record
    assert len(tuple(settings.root.glob('tool_projection_*.json'))) == 1


def test_local_tool_namespaces_do_not_collide(tmp_path: Path) -> None:
    operations = LocalToolProjectionStore(
        LocalToolProjectionStoreSettings.from_namespace(
            namespace=AdaStorageNamespace(
                application_namespace='conciencia_situacional',
                tool_namespace='operaciones_integradas',
            ),
            base_root=tmp_path,
        )
    )
    mine = LocalToolProjectionStore(
        LocalToolProjectionStoreSettings.from_namespace(
            namespace=AdaStorageNamespace(
                application_namespace='conciencia_situacional',
                tool_namespace='mina',
            ),
            base_root=tmp_path,
        )
    )

    operations_record = _record('operaciones_integradas')
    mine_record = _record('mina')
    operations.replace_active(operations_record)
    mine.replace_active(mine_record)

    assert operations.get_active(SourceKey('tools')) == operations_record
    assert mine.get_active(SourceKey('tools')) == mine_record
