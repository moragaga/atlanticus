# Espejo pedagógico equivalente al código productivo.
from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType

from dotenv import dotenv_values

from ada_command_center.web.tools.discovery_cosmos import ToolCosmosConnectionDeclarations
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.connectivity.storage import (
    StorageConnectionStringCredential,
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
COMMAND_CENTER_NAMESPACE = StorageNamespace('conciencia_situacional', 'command-center')
COMMAND_CENTER_CATALOG_BLOB_NAME = COMMAND_CENTER_NAMESPACE.scope_blob_name(
    'tool-catalog/current.json'
)
_STORAGE_NAMES = (STORAGE_CONNECTION_STRING_VARIABLE, STORAGE_CONTAINER_VARIABLE)
_OWN_NAMES = (
    *_STORAGE_NAMES,
    'ADA_COMMAND_CENTER_COSMOS_ENDPOINT',
    'ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME',
    'ADA_COMMAND_CENTER_COSMOS_KEY',
)
_MANAGER_PROVIDER = 'ADA_MANAGER_PERSISTENCE_PROVIDER'


class CommandCenterConfigurationError(ValueError):
    pass


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

    # Ambos proveedores utilizan exactamente la misma conexión/contendor para el catálogo.
    def storage(self) -> Mapping[str, str]:
        return self._require_names(_STORAGE_NAMES)

    def own(self) -> Mapping[str, str]:
        return self._require_names(_OWN_NAMES)

    # Las conexiones de Tools se resuelven solo cuando una acción administrativa las demanda.
    def external(self) -> Mapping[str, CosmosSettings]:
        declarations = ToolCosmosConnectionDeclarations.discover(self._values)
        required = tuple(name for name, _ in declarations.variable_requirements())
        return declarations.resolve(
            values=self._require_names(required),
            allow_insecure_http=self._environment.is_local,
        )

    def _require_names(self, names: tuple[str, ...]) -> Mapping[str, str]:
        resolved: dict[str, str] = {}
        for name in names:
            value = self._values.get(name)
            if not isinstance(value, str) or not value or value != value.strip():
                raise CommandCenterConfigurationError(f'Unresolved Manager variable: {name}')
            resolved[name] = value
        return MappingProxyType(resolved)


def catalog_storage_settings(values: Mapping[str, str]) -> StorageSettings:
    value = values.get(STORAGE_CONNECTION_STRING_VARIABLE)
    if not isinstance(value, str) or not value or value != value.strip():
        raise CommandCenterConfigurationError(
            f'Missing or invalid Manager variable: {STORAGE_CONNECTION_STRING_VARIABLE}'
        )
    return StorageSettings(credential=StorageConnectionStringCredential(value))
