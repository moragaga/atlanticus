from __future__ import annotations

import ast
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from flask import Flask

from ada.web.kpis.definition.coverage import KpiDefinitionCatalog
from ada.web.kpis.definition.models import (
    KpiDefinition as ConfigurationKpiDefinition,
    KpiDefinitionConfiguration,
)
from ada.web.inspection.api import create_kpi_inspection_api_module
from ada.web.inspection.core import KpiDefinitionSnapshotStore
from ada.web.inspection.providers.kpi_definition import KpiDefinitionProjectionProvider
from ada.web.inspection.runtime import KpiDefinitionRefresh, KpiDefinitionWarmup
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey, SourceReleaseId

_SOURCE_KEY = SourceKey('kpi-definitions')


class InMemoryProjectionStore:
    def __init__(self, projection: ProjectionRecord[KpiDefinitionCatalog] | None) -> None:
        self.projection = projection
        self.requested_keys: list[SourceKey] = []
        self.replace_calls = 0
        self.failure: RuntimeError | None = None

    def get_active(
        self,
        source_key: SourceKey,
    ) -> ProjectionRecord[KpiDefinitionCatalog] | None:
        self.requested_keys.append(source_key)
        if self.failure is not None:
            raise self.failure
        return self.projection

    def replace_active(
        self,
        projection: ProjectionRecord[KpiDefinitionCatalog],
    ) -> ProjectionRecord[KpiDefinitionCatalog]:
        self.replace_calls += 1
        self.projection = projection
        return projection


def _definition(kpi_key: str, **fields: str | None) -> ConfigurationKpiDefinition:
    return ConfigurationKpiDefinition(kpi_key=kpi_key, fields=fields)


def _projection(*definitions: ConfigurationKpiDefinition) -> ProjectionRecord[KpiDefinitionCatalog]:
    projected_at = datetime(2026, 8, 27, 19, 30, tzinfo=UTC)
    return ProjectionRecord(
        source_key=_SOURCE_KEY,
        source_release_id=SourceReleaseId('source-revision'),
        source_published_at_utc=projected_at,
        projected_at_utc=projected_at,
        payload=KpiDefinitionCatalog(
            configuration=KpiDefinitionConfiguration(definitions=definitions),
            coverage=(),
        ),
    )


def _provider(store: InMemoryProjectionStore) -> KpiDefinitionProjectionProvider:
    return KpiDefinitionProjectionProvider(
        projection_store=store,
        source_key=_SOURCE_KEY,
    )


def _server(store: KpiDefinitionSnapshotStore) -> Flask:
    module = create_kpi_inspection_api_module(store)
    server = Flask(__name__)
    services = ServiceRegistry()
    services.freeze()
    assert module.register_routes is not None
    module.register_routes(server, services)
    return server


def test_full_stack_warmup_serves_projection_without_external_infrastructure() -> None:
    projection_store = InMemoryProjectionStore(
        _projection(
            _definition(
                'transported_total',
                description='Transported material',
                unit='kt',
            ),
            _definition('recovery'),
        )
    )
    provider = _provider(projection_store)
    store = KpiDefinitionSnapshotStore()

    KpiDefinitionWarmup(provider, store).run()
    client = _server(store).test_client()

    found = client.get('/api/inspection/kpis/transported_total')
    stub = client.get('/api/inspection/kpis/recovery')
    missing = client.get('/api/inspection/kpis/not_defined')

    assert found.status_code == 200
    assert found.get_json() == {
        'available': True,
        'definition': {'description': 'Transported material', 'unit': 'kt'},
        'kpi_key': 'transported_total',
    }
    assert stub.get_json() == {
        'available': True,
        'definition': {},
        'kpi_key': 'recovery',
    }
    assert missing.get_json() == {
        'available': False,
        'definition': None,
        'kpi_key': 'not_defined',
    }
    assert projection_store.requested_keys == [_SOURCE_KEY]
    assert projection_store.replace_calls == 0


def test_empty_projection_warmup_is_valid_and_api_reports_unavailable() -> None:
    projection_store = InMemoryProjectionStore(None)
    store = KpiDefinitionSnapshotStore()

    KpiDefinitionWarmup(_provider(projection_store), store).run()
    response = _server(store).test_client().get('/api/inspection/kpis/transported_total')

    assert response.status_code == 200
    assert response.get_json() == {
        'available': False,
        'definition': None,
        'kpi_key': 'transported_total',
    }
    assert projection_store.requested_keys == [_SOURCE_KEY]


def test_api_click_path_never_reads_projection_store_after_warmup() -> None:
    projection_store = InMemoryProjectionStore(
        _projection(_definition('transported_total', description='Transported material'))
    )
    provider = _provider(projection_store)
    store = KpiDefinitionSnapshotStore()
    KpiDefinitionWarmup(provider, store).run()
    client = _server(store).test_client()

    for kpi_key in ('transported_total', 'missing', 'transported_total', 'missing'):
        response = client.get(f'/api/inspection/kpis/{kpi_key}')
        assert response.status_code == 200

    assert projection_store.requested_keys == [_SOURCE_KEY]
    assert projection_store.replace_calls == 0


def test_explicit_refresh_updates_live_api_without_rebuilding_server() -> None:
    projection_store = InMemoryProjectionStore(
        _projection(_definition('transported_total', description='Old definition'))
    )
    provider = _provider(projection_store)
    store = KpiDefinitionSnapshotStore()
    KpiDefinitionWarmup(provider, store).run()
    server = _server(store)
    client = server.test_client()

    before = client.get('/api/inspection/kpis/transported_total')
    projection_store.projection = _projection(
        _definition('availability', description='New definition')
    )
    KpiDefinitionRefresh(provider, store).run()
    previous = client.get('/api/inspection/kpis/transported_total')
    current = client.get('/api/inspection/kpis/availability')

    assert before.get_json()['definition'] == {'description': 'Old definition'}
    assert previous.get_json() == {
        'available': False,
        'definition': None,
        'kpi_key': 'transported_total',
    }
    assert current.get_json()['definition'] == {'description': 'New definition'}
    assert projection_store.requested_keys == [_SOURCE_KEY, _SOURCE_KEY]


def test_failed_refresh_preserves_last_valid_snapshot_served_by_api() -> None:
    projection_store = InMemoryProjectionStore(
        _projection(_definition('transported_total', description='Last valid definition'))
    )
    provider = _provider(projection_store)
    store = KpiDefinitionSnapshotStore()
    KpiDefinitionWarmup(provider, store).run()
    client = _server(store).test_client()
    projection_store.failure = RuntimeError('Projection unavailable')

    with pytest.raises(RuntimeError, match='Projection unavailable'):
        KpiDefinitionRefresh(provider, store).run()

    response = client.get('/api/inspection/kpis/transported_total')
    assert response.status_code == 200
    assert response.get_json()['definition'] == {'description': 'Last valid definition'}
    assert projection_store.requested_keys == [_SOURCE_KEY, _SOURCE_KEY]


def test_portability_dependency_graph_has_no_direct_azure_or_cosmos_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    capability_roots = (
        root / '../../kpis/definition/core',
        root / '../core',
        root / '../providers/kpi-definition',
        root / '../runtime',
        root / '../api',
        root,
    )

    imported_modules: set[str] = set()
    dependencies: list[str] = []
    for capability_root in capability_roots:
        resolved = capability_root.resolve()
        project = tomllib.loads((resolved / 'pyproject.toml').read_text(encoding='utf-8'))
        dependencies.extend(project.get('project', {}).get('dependencies', []))
        for path in (resolved / 'src').rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_modules.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module is not None:
                    imported_modules.add(node.module)

    blocked_imports = tuple(
        name
        for name in imported_modules
        if name == 'azure'
        or name.startswith('azure.')
        or name == 'cosmos'
        or name.startswith('cosmos.')
    )
    blocked_dependencies = tuple(
        dependency
        for dependency in dependencies
        if 'azure' in dependency.lower() or 'cosmos' in dependency.lower()
    )

    assert blocked_imports == ()
    assert blocked_dependencies == ()
