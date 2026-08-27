from __future__ import annotations

import ast
import tomllib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from flask import Flask

from ada.configuration.kpi_definition import (
    KpiDefinition as ConfigurationKpiDefinition,
    KpiDefinitionConfiguration,
    KpiDefinitionProjection,
)
from ada.web.inspection.api import create_kpi_inspection_api_module
from ada.web.inspection.core import KpiDefinitionSnapshotStore
from ada.web.inspection.providers.kpi_definition import KpiDefinitionProjectionProvider
from ada.web.inspection.runtime import KpiDefinitionRefresh, KpiDefinitionWarmup
from atlanticus.web.services import ServiceRegistry


class InMemoryProjectionRepository:
    def __init__(self, projection: KpiDefinitionProjection | None) -> None:
        self.projection = projection
        self.load_calls = 0
        self.save_calls = 0
        self.health_calls = 0
        self.failure: RuntimeError | None = None

    def load(self) -> KpiDefinitionProjection | None:
        self.load_calls += 1
        if self.failure is not None:
            raise self.failure
        return self.projection

    def save(self, projection: KpiDefinitionProjection) -> KpiDefinitionProjection:
        self.save_calls += 1
        self.projection = projection
        return projection

    def health_check(self) -> bool:
        self.health_calls += 1
        return True


def _definition(kpi_key: str, **fields: str | None) -> ConfigurationKpiDefinition:
    return ConfigurationKpiDefinition(kpi_key=kpi_key, fields=fields)


def _projection(*definitions: ConfigurationKpiDefinition) -> KpiDefinitionProjection:
    return KpiDefinitionProjection.create(
        configuration=KpiDefinitionConfiguration(definitions=definitions),
        source_revision='source-revision',
        projected_by='portability-gate',
        projected_at_utc=datetime(2026, 8, 27, 19, 30, tzinfo=UTC),
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
    repository = InMemoryProjectionRepository(
        _projection(
            _definition(
                'transported_total',
                description='Transported material',
                unit='kt',
            ),
            _definition('recovery'),
        )
    )
    provider = KpiDefinitionProjectionProvider(repository)
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
    assert repository.load_calls == 1
    assert repository.save_calls == 0
    assert repository.health_calls == 0


def test_empty_projection_warmup_is_valid_and_api_reports_unavailable() -> None:
    repository = InMemoryProjectionRepository(None)
    store = KpiDefinitionSnapshotStore()

    KpiDefinitionWarmup(KpiDefinitionProjectionProvider(repository), store).run()
    response = _server(store).test_client().get('/api/inspection/kpis/transported_total')

    assert response.status_code == 200
    assert response.get_json() == {
        'available': False,
        'definition': None,
        'kpi_key': 'transported_total',
    }
    assert repository.load_calls == 1


def test_api_click_path_never_reads_repository_after_warmup() -> None:
    repository = InMemoryProjectionRepository(
        _projection(_definition('transported_total', description='Transported material'))
    )
    provider = KpiDefinitionProjectionProvider(repository)
    store = KpiDefinitionSnapshotStore()
    KpiDefinitionWarmup(provider, store).run()
    client = _server(store).test_client()

    for kpi_key in ('transported_total', 'missing', 'transported_total', 'missing'):
        response = client.get(f'/api/inspection/kpis/{kpi_key}')
        assert response.status_code == 200

    assert repository.load_calls == 1
    assert repository.save_calls == 0
    assert repository.health_calls == 0


def test_explicit_refresh_updates_live_api_without_rebuilding_server() -> None:
    repository = InMemoryProjectionRepository(
        _projection(_definition('transported_total', description='Old definition'))
    )
    provider = KpiDefinitionProjectionProvider(repository)
    store = KpiDefinitionSnapshotStore()
    KpiDefinitionWarmup(provider, store).run()
    server = _server(store)
    client = server.test_client()

    before = client.get('/api/inspection/kpis/transported_total')
    repository.projection = _projection(_definition('availability', description='New definition'))
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
    assert repository.load_calls == 2


def test_failed_refresh_preserves_last_valid_snapshot_served_by_api() -> None:
    repository = InMemoryProjectionRepository(
        _projection(_definition('transported_total', description='Last valid definition'))
    )
    provider = KpiDefinitionProjectionProvider(repository)
    store = KpiDefinitionSnapshotStore()
    KpiDefinitionWarmup(provider, store).run()
    client = _server(store).test_client()
    repository.failure = RuntimeError('Projection unavailable')

    with pytest.raises(RuntimeError, match='Projection unavailable'):
        KpiDefinitionRefresh(provider, store).run()

    response = client.get('/api/inspection/kpis/transported_total')
    assert response.status_code == 200
    assert response.get_json()['definition'] == {'description': 'Last valid definition'}
    assert repository.load_calls == 2


def test_portability_dependency_graph_has_no_direct_azure_or_cosmos_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    capability_roots = (
        root / '../../configuration/kpi-definition',
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
