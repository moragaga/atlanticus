# Las declaraciones proceden de nombres de variables inyectados o del manifiesto, nunca de Key Vault enumerado.
from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from types import MappingProxyType

from ada_command_center.web.tools.discovery_cosmos.discovery import ToolCatalogDiscovery
from atlanticus.connectivity.cosmos import CosmosClient, CosmosSettings

TOOL_COSMOS_PREFIX = 'ADA_COMMAND_CENTER_TOOL_COSMOS_'
_CONNECTION_NAME = re.compile(r'[A-Z][A-Z0-9_]{0,62}\Z')
_VARIABLE_SUFFIXES = ('DATABASE_NAME', 'ENDPOINT', 'KEY')
_MAX_CONNECTIONS = 256


class ToolCosmosConnectionConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ToolCosmosConnectionDeclaration:
    connection_name: str
    endpoint_var: str
    database_var: str
    credential_var: str

    def variable_requirements(self) -> tuple[tuple[str, bool], ...]:
        return (
            (self.endpoint_var, False),
            (self.database_var, False),
            (self.credential_var, True),
        )


@dataclass(frozen=True, slots=True)
# Este contrato descubre conexiones, no Tools; las tool_key reales se leen desde Cosmos.
class ToolCosmosConnectionDeclarations:
    connections: tuple[ToolCosmosConnectionDeclaration, ...]

    @classmethod
    # La lista de variables puede provenir del .env local o de secrets.json en despliegue.
    def discover(cls, variable_names: Iterable[str]) -> ToolCosmosConnectionDeclarations:
        if isinstance(variable_names, str | bytes):
            raise TypeError('Variable names must be an iterable of names')
        try:
            names = tuple(variable_names)
        except TypeError:
            raise TypeError('Variable names must be iterable') from None
        if any(not isinstance(name, str) for name in names):
            raise TypeError('Variable names must be text')
        if len(names) != len(set(names)):
            raise ToolCosmosConnectionConfigurationError('Duplicate connection variables')
        groups: dict[str, set[str]] = {}
        for variable in names:
            if not variable.startswith(TOOL_COSMOS_PREFIX):
                continue
            tail = variable[len(TOOL_COSMOS_PREFIX) :]
            matched = next(
                (field for field in _VARIABLE_SUFFIXES if tail.endswith('_' + field)),
                None,
            )
            if matched is None:
                raise ToolCosmosConnectionConfigurationError('Unsupported Tool Cosmos variable')
            connection = tail[: -(len(matched) + 1)]
            if _CONNECTION_NAME.fullmatch(connection) is None or connection == 'COMMAND_CENTER':
                raise ToolCosmosConnectionConfigurationError('Invalid Tool Cosmos connection name')
            groups.setdefault(connection, set()).add(matched)
        if not groups:
            raise ToolCosmosConnectionConfigurationError(
                'No external Tool Cosmos connections declared'
            )
        if len(groups) > _MAX_CONNECTIONS:
            raise ToolCosmosConnectionConfigurationError('Too many Tool Cosmos connections')
        expected = set(_VARIABLE_SUFFIXES)
        for name, fields in groups.items():
            if fields != expected:
                raise ToolCosmosConnectionConfigurationError(
                    f'Incomplete Tool Cosmos connection: {name.lower()}'
                )
        return cls(
            connections=tuple(
                ToolCosmosConnectionDeclaration(
                    connection_name=name.lower(),
                    endpoint_var=f'{TOOL_COSMOS_PREFIX}{name}_ENDPOINT',
                    database_var=f'{TOOL_COSMOS_PREFIX}{name}_DATABASE_NAME',
                    credential_var=f'{TOOL_COSMOS_PREFIX}{name}_KEY',
                )
                for name in sorted(groups)
            )
        )

    def variable_requirements(self) -> tuple[tuple[str, bool], ...]:
        return tuple(
            requirement
            for connection in self.connections
            for requirement in connection.variable_requirements()
        )

    # El host ya resolvió secretos; aquí no se leen valores desde el navegador.
    def resolve(
        self,
        *,
        values: Mapping[str, str],
        allow_insecure_http: bool = False,
    ) -> Mapping[str, CosmosSettings]:
        if not isinstance(values, Mapping):
            raise TypeError('Resolved configuration must be a mapping')
        if not isinstance(allow_insecure_http, bool):
            raise TypeError('allow_insecure_http must be a boolean')
        resolved: dict[str, CosmosSettings] = {}
        for item in self.connections:
            try:
                endpoint = values[item.endpoint_var]
                database = values[item.database_var]
                credential = values[item.credential_var]
            except KeyError:
                raise ToolCosmosConnectionConfigurationError(
                    f'Unresolved Tool Cosmos connection: {item.connection_name}'
                ) from None
            if any(
                not isinstance(value, str) or not value or value != value.strip()
                for value in (endpoint, database, credential)
            ):
                raise ToolCosmosConnectionConfigurationError(
                    f'Invalid Tool Cosmos connection: {item.connection_name}'
                )
            try:
                resolved[item.connection_name] = CosmosSettings(
                    endpoint=endpoint,
                    database_name=database,
                    key=credential,
                    allow_insecure_http=allow_insecure_http,
                )
            except TypeError, ValueError:
                raise ToolCosmosConnectionConfigurationError(
                    f'Invalid Tool Cosmos connection: {item.connection_name}'
                ) from None
        return MappingProxyType(resolved)


def _create_client(settings: CosmosSettings) -> CosmosClient:
    return CosmosClient(settings=settings)


# La exploración abre y cierra clientes exclusivamente al invocarse esta operación.
@contextmanager
def open_tool_catalog_discovery(
    *,
    external_connections: Mapping[str, CosmosSettings],
    client_factory: Callable[[CosmosSettings], CosmosClient] = _create_client,
) -> Iterator[ToolCatalogDiscovery]:
    if not isinstance(external_connections, Mapping) or not external_connections:
        raise ValueError('External Tool Cosmos connections are required')
    if not callable(client_factory):
        raise TypeError('client_factory must be callable')
    if any(
        not isinstance(name, str)
        or _CONNECTION_NAME.fullmatch(name.upper()) is None
        or name != name.lower()
        or name == 'command_center'
        or not isinstance(settings, CosmosSettings)
        for name, settings in external_connections.items()
    ):
        raise TypeError('Invalid external Tool Cosmos connections')
    with ExitStack() as stack:
        clients: dict[str, CosmosClient] = {}
        for name, settings in sorted(external_connections.items()):
            client = client_factory(settings)
            if not isinstance(client, CosmosClient):
                raise TypeError('client_factory must return CosmosClient')
            stack.callback(client.close)
            clients[name] = client
        yield ToolCatalogDiscovery(connections=clients)
