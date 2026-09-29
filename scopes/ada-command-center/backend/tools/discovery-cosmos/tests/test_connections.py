from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from ada_command_center.tools.discovery_cosmos import (
    ToolCatalogConnectionStatus,
    ToolCosmosConnectionConfigurationError,
    ToolCosmosConnectionDeclarations,
    open_tool_catalog_discovery,
)
from atlanticus.connectivity.cosmos import CosmosClient, CosmosSettings


class CosmosStub(CosmosClient):
    def __init__(self, settings: CosmosSettings) -> None:
        self.settings = settings
        self.closed = False
        self.queries = 0

    def query_items(self, **kwargs):
        self.queries += 1
        return ()

    def close(self) -> None:
        self.closed = True


def _values(*names: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for index, name in enumerate(names):
        prefix = f'ADA_COMMAND_CENTER_TOOL_COSMOS_{name}_'
        values[prefix + 'ENDPOINT'] = f'https://{name.lower()}-{index}.example.com'
        values[prefix + 'DATABASE_NAME'] = f'db-{index}'
        values[prefix + 'KEY'] = f'secret-{index}'
    return values


def test_dynamic_discovery_without_manual_connection_listing() -> None:
    values = _values('MINA', 'OPERACIONES_INTEGRADAS', 'FLOTACION_SELECTIVA')
    values['ADA_COMMAND_CENTER_COSMOS_ENDPOINT'] = 'https://command-center.example.com'
    declarations = ToolCosmosConnectionDeclarations.discover(values)
    assert tuple(item.connection_name for item in declarations.connections) == (
        'flotacion_selectiva',
        'mina',
        'operaciones_integradas',
    )
    assert len(declarations.variable_requirements()) == 9
    resolved = declarations.resolve(values=values)
    assert tuple(resolved) == ('flotacion_selectiva', 'mina', 'operaciones_integradas')
    assert resolved['mina'].database_name == 'db-0'
    with pytest.raises(TypeError):
        resolved['another'] = resolved['mina']


def test_manifest_only_names_can_discover_before_secret_resolution() -> None:
    values = _values('MINA')
    declarations = ToolCosmosConnectionDeclarations.discover(values.keys())
    assert ('ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_KEY', True) in (
        declarations.variable_requirements()
    )
    values['ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_KEY'] = 'injected-secret'
    assert declarations.resolve(values=values)['mina'].key == 'injected-secret'


@pytest.mark.parametrize('removed', ['ENDPOINT', 'DATABASE_NAME', 'KEY'])
def test_incomplete_connections_fail_without_silent_omission(removed: str) -> None:
    values = _values('MINA', 'PLANTA')
    del values[f'ADA_COMMAND_CENTER_TOOL_COSMOS_PLANTA_{removed}']
    with pytest.raises(ToolCosmosConnectionConfigurationError, match='Incomplete'):
        ToolCosmosConnectionDeclarations.discover(values)


def test_invalid_variable_and_empty_configuration_are_rejected() -> None:
    with pytest.raises(ToolCosmosConnectionConfigurationError, match='No external'):
        ToolCosmosConnectionDeclarations.discover({'ADA_COMMAND_CENTER_COSMOS_KEY': 'own'})
    values = _values('MINA')
    values['ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_TIMEOUT'] = '30'
    with pytest.raises(ToolCosmosConnectionConfigurationError, match='Unsupported'):
        ToolCosmosConnectionDeclarations.discover(values)


def test_invalid_connection_names_and_duplicate_variables_are_rejected() -> None:
    values = _values('MINA')
    values['ADA_COMMAND_CENTER_TOOL_COSMOS_COMMAND_CENTER_KEY'] = 'incorrect'
    with pytest.raises(ToolCosmosConnectionConfigurationError):
        ToolCosmosConnectionDeclarations.discover(values)
    names = list(_values('MINA'))
    with pytest.raises(ToolCosmosConnectionConfigurationError, match='Duplicate'):
        ToolCosmosConnectionDeclarations.discover(names + [names[0]])


def test_missing_resolved_secret_does_not_disclose_values() -> None:
    values = _values('MINA')
    declarations = ToolCosmosConnectionDeclarations.discover(values)
    del values['ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_KEY']
    values['ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_ENDPOINT'] = 'https://sensitive.example.com'
    with pytest.raises(ToolCosmosConnectionConfigurationError) as error:
        declarations.resolve(values=values)
    assert 'sensitive' not in str(error.value)


def test_invalid_cosmos_settings_do_not_disclose_values() -> None:
    values = _values('MINA')
    declarations = ToolCosmosConnectionDeclarations.discover(values)
    values['ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_ENDPOINT'] = 'not-an-endpoint'
    values['ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_KEY'] = 'VERY_SECRET_VALUE'
    with pytest.raises(ToolCosmosConnectionConfigurationError) as error:
        declarations.resolve(values=values)
    assert 'VERY_SECRET_VALUE' not in str(error.value)
    assert 'not-an-endpoint' not in str(error.value)


def test_local_http_requires_explicit_permission() -> None:
    values = _values('MINA')
    values['ADA_COMMAND_CENTER_TOOL_COSMOS_MINA_ENDPOINT'] = 'http://localhost:8081'
    declarations = ToolCosmosConnectionDeclarations.discover(values)
    with pytest.raises(ToolCosmosConnectionConfigurationError):
        declarations.resolve(values=values)
    assert declarations.resolve(values=values, allow_insecure_http=True)['mina'].allow_insecure_http


def test_own_connection_is_not_created_and_clients_close_after_inspection() -> None:
    created: list[CosmosStub] = []

    def factory(settings: CosmosSettings) -> CosmosStub:
        client = CosmosStub(settings)
        created.append(client)
        return client

    values = _values('MINA', 'PLANTA')
    declarations = ToolCosmosConnectionDeclarations.discover(values)
    resolved = declarations.resolve(values=values)
    assert created == []
    with open_tool_catalog_discovery(
        external_connections=resolved, client_factory=factory
    ) as service:
        report = service.inspect()
        assert tuple(record.connection_name for record in report.connections) == (
            'mina',
            'planta',
        )
        assert all(
            record.status is ToolCatalogConnectionStatus.NO_TOOLS for record in report.connections
        )
        assert all(client.queries == 1 and not client.closed for client in created)
    assert len(created) == 2
    assert all(client.closed for client in created)


def test_factory_failure_closes_earlier_clients() -> None:
    created: list[CosmosStub] = []

    def factory(settings: CosmosSettings) -> CosmosStub:
        if len(created) == 1:
            raise RuntimeError('factory failed')
        client = CosmosStub(settings)
        created.append(client)
        return client

    values = _values('MINA', 'PLANTA')
    connections = ToolCosmosConnectionDeclarations.discover(values).resolve(values=values)
    with (
        pytest.raises(RuntimeError, match='factory failed'),
        open_tool_catalog_discovery(external_connections=connections, client_factory=factory),
    ):
        pass
    assert created[0].closed


def test_context_failure_closes_clients() -> None:
    created: list[CosmosStub] = []

    def factory(settings: CosmosSettings) -> CosmosStub:
        client = CosmosStub(settings)
        created.append(client)
        return client

    values = _values('MINA')
    connections = ToolCosmosConnectionDeclarations.discover(values).resolve(values=values)
    with (
        pytest.raises(RuntimeError, match='aborted'),
        open_tool_catalog_discovery(external_connections=connections, client_factory=factory),
    ):
        raise RuntimeError('aborted')
    assert created[0].closed


def test_invalid_external_connections_fail_before_opening() -> None:
    calls = []

    def factory(settings: CosmosSettings) -> CosmosStub:
        calls.append(settings)
        return CosmosStub(settings)

    first = CosmosSettings(endpoint='https://mine.example.com', database_name='mine', key='s')
    cases: tuple[Mapping[str, CosmosSettings], ...] = (
        {},
        {'command_center': first},
        {'MINA': first},
    )
    for case in cases:
        with (
            pytest.raises((ValueError, TypeError)),
            open_tool_catalog_discovery(external_connections=case, client_factory=factory),
        ):
            pass
    assert not calls


def test_dynamic_discovery_to_existing_confirmed_catalog_without_extra_registry() -> None:
    from ada_command_center.tools.catalog import ToolCatalogConsolidator

    from .test_discovery import CatalogStoreStub, CosmosStub as ProjectionCosmosStub, _seed

    created = []

    class ClosingProjectionStub(ProjectionCosmosStub):
        def __init__(self):
            super().__init__()
            self.closed = False

        def close(self):
            self.closed = True

    def factory(settings: CosmosSettings):
        client = ClosingProjectionStub()
        tool_key = 'mine' if settings.database_name == 'db-0' else 'flotation'
        _seed(client, namespace=tool_key, tool_key=tool_key)
        created.append(client)
        return client

    values = _values('MINA', 'FLOTACION_SELECTIVA')
    connections = ToolCosmosConnectionDeclarations.discover(values).resolve(values=values)
    with open_tool_catalog_discovery(
        external_connections=connections, client_factory=factory
    ) as discovery:
        report = discovery.inspect()
        store = CatalogStoreStub()
        confirmed = ToolCatalogConsolidator(
            inputs=report.consolidation_inputs(current=store.get_current()),
            store=store,
            clock=lambda: datetime(2026, 9, 29, tzinfo=UTC),
        ).refresh()
        assert tuple(item.tool_key for item in confirmed.tools) == ('flotation', 'mine')
        assert store.get_current() == confirmed
    assert all(client.closed for client in created)
