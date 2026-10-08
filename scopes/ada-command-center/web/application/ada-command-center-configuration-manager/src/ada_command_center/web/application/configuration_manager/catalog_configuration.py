from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlsplit

from dotenv import dotenv_values

from ada_command_center.web.tools.discovery_cosmos import ToolCosmosConnectionDeclarations
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.connectivity.storage import (
    StorageConnectionStringCredential,
    StorageSasCredential,
    StorageSettings,
)
from atlanticus.web.configuration import (
    ATLANTICUS_ENVIRONMENT_VARIABLE,
    WebEnvironment,
    WebSettings,
)
from atlanticus.web.storage.namespace import StorageNamespace

STORAGE_CONNECTION_STRING_VARIABLE = 'ADA_COMMAND_CENTER_STORAGE_CONNECTION_STRING'
STORAGE_CONTAINER_VARIABLE = 'ADA_COMMAND_CENTER_STORAGE_CONTAINER_NAME'
STORAGE_ACCOUNT_URL_VARIABLE = 'ADA_COMMAND_CENTER_STORAGE_ACCOUNT_URL'
STORAGE_SAS_TOKEN_VARIABLE = 'ADA_COMMAND_CENTER_STORAGE_SAS_TOKEN'
APPLICATION_NAMESPACE_VARIABLE = 'ADA_APPLICATION_NAMESPACE'
TOOL_NAMESPACE_VARIABLE = 'ADA_TOOL_NAMESPACE'
_COSMOS_NAMES = (
    'ADA_COMMAND_CENTER_COSMOS_ENDPOINT',
    'ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME',
    'ADA_COMMAND_CENTER_COSMOS_KEY',
)
_MANAGER_PROVIDER = 'ADA_MANAGER_PERSISTENCE_PROVIDER'


class CommandCenterConfigurationError(ValueError):
    pass


def resolve_command_center_namespace(values: Mapping[str, str]) -> StorageNamespace:
    for name in (APPLICATION_NAMESPACE_VARIABLE, TOOL_NAMESPACE_VARIABLE):
        if name not in values:
            raise CommandCenterConfigurationError(f'Unresolved Manager variable: {name}')
    try:
        return StorageNamespace(
            application_namespace=values[APPLICATION_NAMESPACE_VARIABLE],
            scope_namespace=values[TOOL_NAMESPACE_VARIABLE],
        )
    except (TypeError, ValueError) as error:
        raise CommandCenterConfigurationError('Invalid Command Center Storage namespace') from error


def _cosmos_identity(endpoint: str, database: str) -> tuple[str, str, int | None, str, str]:
    parsed = urlsplit(endpoint)
    port = parsed.port
    if port is None:
        port = {'http': 80, 'https': 443}.get(parsed.scheme.lower())
    return (parsed.scheme.lower(), (parsed.hostname or '').lower(), port,
            parsed.path.rstrip('/'), database)


class ManagerConfigurationReader:
    def __init__(
        self,
        *,
        root: Path,
        environ_supplier: Callable[[], Mapping[str, str]] | None = None,
    ) -> None:
        if not isinstance(root, Path):
            raise TypeError('root must be a Path')
        supplier = environ_supplier or (lambda: os.environ)
        if not callable(supplier):
            raise TypeError('environ_supplier must be callable')
        process = dict(supplier())
        if any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in process.items()
        ):
            raise CommandCenterConfigurationError('Host configuration must contain text values')
        if process.get(ATLANTICUS_ENVIRONMENT_VARIABLE) == WebEnvironment.PRODUCTION.value:
            effective = process
        else:
            local = dotenv_values(root / '.env', interpolate=False)
            effective = {
                **{name: value for name, value in local.items() if isinstance(value, str)},
                **process,
            }
        try:
            environment = WebSettings.from_mapping(effective).environment
        except ValueError:
            raise CommandCenterConfigurationError('Invalid Atlanticus Web environment') from None
        if environment is WebEnvironment.PRODUCTION and (
            process.get(ATLANTICUS_ENVIRONMENT_VARIABLE) != WebEnvironment.PRODUCTION.value
        ):
            raise CommandCenterConfigurationError(
                'Production Web environment must be explicitly supplied by the host'
            )
        self._values = MappingProxyType(effective)
        self._environment = environment

    @property
    def environment(self) -> WebEnvironment:
        return self._environment

    @property
    def manager_provider(self) -> str:
        mode = self._values.get(_MANAGER_PROVIDER, 'local')
        if mode not in ('local', 'durable'):
            raise CommandCenterConfigurationError('Unsupported Command Center Manager provider')
        if self.environment is WebEnvironment.PRODUCTION and mode != 'durable':
            raise CommandCenterConfigurationError('Production Manager requires durable provider')
        return mode

    @property
    def namespace(self) -> StorageNamespace:
        return resolve_command_center_namespace(self._values)

    def storage(self) -> Mapping[str, str]:
        container = self._require_names((STORAGE_CONTAINER_VARIABLE,))
        connection = self._values.get(STORAGE_CONNECTION_STRING_VARIABLE)
        account = self._values.get(STORAGE_ACCOUNT_URL_VARIABLE)
        sas = self._values.get(STORAGE_SAS_TOKEN_VARIABLE)
        if connection is not None:
            if account is not None or sas is not None:
                raise CommandCenterConfigurationError('Storage credentials are mutually exclusive')
            credentials = self._require_names((STORAGE_CONNECTION_STRING_VARIABLE,))
        else:
            if account is None and sas is None:
                raise CommandCenterConfigurationError(
                    'Storage requires connection string or account URL plus SAS token'
                )
            credentials = self._require_names(
                (STORAGE_ACCOUNT_URL_VARIABLE, STORAGE_SAS_TOKEN_VARIABLE)
            )
        return MappingProxyType({**container, **credentials})

    def own(self) -> Mapping[str, str]:
        namespace = self.namespace
        return MappingProxyType({
            **self.storage(),
            **self._require_names(_COSMOS_NAMES),
            APPLICATION_NAMESPACE_VARIABLE: namespace.application_namespace,
            TOOL_NAMESPACE_VARIABLE: namespace.scope_namespace,
        })

    def external(self) -> Mapping[str, CosmosSettings]:
        declarations = ToolCosmosConnectionDeclarations.discover(self._values)
        required = tuple(name for name, _ in declarations.variable_requirements())
        resolved = declarations.resolve(
            values=self._require_names(required),
            allow_insecure_http=self._environment.is_local,
        )
        own_endpoint = self._values.get('ADA_COMMAND_CENTER_COSMOS_ENDPOINT')
        own_database = self._values.get('ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME')
        if self._values.get(_MANAGER_PROVIDER) == 'durable':
            own = self._require_names(_COSMOS_NAMES)
            own_endpoint = own['ADA_COMMAND_CENTER_COSMOS_ENDPOINT']
            own_database = own['ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME']
        if isinstance(own_endpoint, str) and isinstance(own_database, str):
            own_identity = _cosmos_identity(own_endpoint, own_database)
            if any(
                _cosmos_identity(settings.endpoint, settings.database_name) == own_identity
                for settings in resolved.values()
            ):
                raise CommandCenterConfigurationError(
                    'External Tool Cosmos must not target the Command Center database'
                )
        return resolved

    def _require_names(self, names: tuple[str, ...]) -> Mapping[str, str]:
        resolved: dict[str, str] = {}
        for name in names:
            value = self._values.get(name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise CommandCenterConfigurationError(f'Unresolved Manager variable: {name}')
            resolved[name] = value
        return MappingProxyType(resolved)


def catalog_storage_settings(
    values: Mapping[str, str], *, allow_insecure_http: bool = False
) -> StorageSettings:
    connection = values.get(STORAGE_CONNECTION_STRING_VARIABLE)
    account = values.get(STORAGE_ACCOUNT_URL_VARIABLE)
    sas = values.get(STORAGE_SAS_TOKEN_VARIABLE)
    if connection is not None:
        if account is not None or sas is not None:
            raise CommandCenterConfigurationError('Storage credentials are mutually exclusive')
        if not isinstance(connection, str) or not connection or connection != connection.strip():
            raise CommandCenterConfigurationError('Invalid Command Center Storage connection string')
        return StorageSettings(credential=StorageConnectionStringCredential(connection))
    if (
        not isinstance(account, str) or not account or account != account.strip()
        or not isinstance(sas, str) or not sas or sas != sas.strip()
    ):
        raise CommandCenterConfigurationError(
            'Storage requires connection string or account URL plus SAS token'
        )
    return StorageSettings(
        credential=StorageSasCredential(
            account_url=account, sas_token=sas, allow_insecure_http=allow_insecure_http
        )
    )
