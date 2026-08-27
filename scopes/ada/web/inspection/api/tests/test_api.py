from flask import Flask

from ada.web.inspection.api import create_kpi_inspection_api_module
from ada.web.inspection.core import (
    KpiDefinition,
    KpiDefinitionSnapshot,
    KpiDefinitionSnapshotStore,
)
from atlanticus.web.services import ServiceRegistry


def _server(store: KpiDefinitionSnapshotStore) -> Flask:
    module = create_kpi_inspection_api_module(store)
    server = Flask(__name__)
    services = ServiceRegistry()
    services.freeze()
    assert module.register_routes is not None
    module.register_routes(server, services)
    return server


def _snapshot(description: str) -> KpiDefinitionSnapshot:
    return KpiDefinitionSnapshot(
        definitions=(
            KpiDefinition(
                kpi_key='transported_total',
                fields={
                    'description': description,
                    'unit': 'kt',
                    'source': 'KPI Configuration Projection',
                },
            ),
        )
    )


def test_found_kpi_returns_definition_from_memory() -> None:
    store = KpiDefinitionSnapshotStore(_snapshot('Transported material'))
    response = _server(store).test_client().get('/api/inspection/kpis/transported_total')

    assert response.status_code == 200
    assert response.get_json() == {
        'available': True,
        'definition': {
            'description': 'Transported material',
            'source': 'KPI Configuration Projection',
            'unit': 'kt',
        },
        'kpi_key': 'transported_total',
    }
    assert response.headers['Cache-Control'] == 'no-store'


def test_missing_kpi_is_available_false_without_error_status() -> None:
    store = KpiDefinitionSnapshotStore(_snapshot('Transported material'))
    response = _server(store).test_client().get('/api/inspection/kpis/not_configured')

    assert response.status_code == 200
    assert response.get_json() == {
        'available': False,
        'definition': None,
        'kpi_key': 'not_configured',
    }
    assert response.headers['Cache-Control'] == 'no-store'


def test_endpoint_observes_replaced_snapshot_without_rebuilding_module() -> None:
    store = KpiDefinitionSnapshotStore(_snapshot('Old definition'))
    server = _server(store)
    client = server.test_client()

    first = client.get('/api/inspection/kpis/transported_total')
    store.replace(_snapshot('New definition'))
    second = client.get('/api/inspection/kpis/transported_total')

    assert first.get_json()['definition']['description'] == 'Old definition'
    assert second.get_json()['definition']['description'] == 'New definition'


def test_missing_lookup_does_not_mutate_snapshot() -> None:
    store = KpiDefinitionSnapshotStore(_snapshot('Transported material'))
    client = _server(store).test_client()

    assert client.get('/api/inspection/kpis/not_configured').get_json()['available'] is False
    assert store.get('transported_total') is not None
    assert store.get('not_configured') is None


def test_blank_kpi_key_returns_english_client_error() -> None:
    store = KpiDefinitionSnapshotStore(_snapshot('Transported material'))
    response = _server(store).test_client().get('/api/inspection/kpis/%20%20%20')

    assert response.status_code == 400
    assert response.get_json() == {'error': 'KPI key must be a non-empty string'}
    assert response.headers['Cache-Control'] == 'no-store'


def test_endpoint_is_read_only() -> None:
    store = KpiDefinitionSnapshotStore(_snapshot('Transported material'))
    response = _server(store).test_client().post('/api/inspection/kpis/transported_total')

    assert response.status_code == 405


def test_factory_rejects_non_store_dependency() -> None:
    try:
        create_kpi_inspection_api_module(object())  # type: ignore[arg-type]
    except TypeError as error:
        assert str(error) == 'Store must be a KpiDefinitionSnapshotStore'
    else:
        raise AssertionError('Expected TypeError')
