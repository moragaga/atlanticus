from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from atlanticus.configuration import ConfigurationVariableSpec
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.kernel import Environment

_REF = re.compile(r'[a-z][a-z0-9_-]{0,63}\Z')
_VARIABLE = re.compile(r'[A-Z][A-Z0-9_]*\Z')
_MAX_FILE_BYTES = 65536
_FILE = Path('config/connections.json')
_FIELDS = frozenset({'endpoint_var', 'database_var', 'credential_var'})


# Diferencia la configuración inválida de la ausencia legítima del archivo.
class AlarmDeliveryConnectionsError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
# Define la referencia lógica y las variables que resolverán cada Cosmos.
class CosmosConnectionDeclaration:
    connection_ref: str
    endpoint_var: str
    database_var: str
    credential_var: str


@dataclass(frozen=True, slots=True)
# Representa un registro inmutable durante toda la ejecución del job.
class AlarmDeliveryConnectionRegistry:
    declarations: tuple[CosmosConnectionDeclaration, ...]

    # Declara las variables dinámicas antes de cargar .env o el manifiesto de secretos.
    def configuration_specs(self) -> tuple[ConfigurationVariableSpec, ...]:
        names: dict[str, bool] = {}
        for entry in self.declarations:
            for name, sensitive in (
                (entry.endpoint_var, False),
                (entry.database_var, False),
                (entry.credential_var, True),
            ):
                names[name] = names.get(name, False) or sensitive
        return tuple(
            ConfigurationVariableSpec(key=name, sensitive=sensitive)
            for name, sensitive in sorted(names.items())
        )

    # Transforma las variables resueltas en contratos Cosmos sin conservar credenciales en JSON.
    def resolve(
        self, *, values: Mapping[str, str], environment: Environment
    ) -> Mapping[str, CosmosSettings]:
        resolved: dict[str, CosmosSettings] = {}
        for declaration in self.declarations:
            try:
                endpoint = values[declaration.endpoint_var]
                database = values[declaration.database_var]
                key = values[declaration.credential_var]
            except KeyError as error:
                raise AlarmDeliveryConnectionsError(
                    f'Connection {declaration.connection_ref} has an unresolved variable'
                ) from error
            try:
                resolved[declaration.connection_ref] = CosmosSettings(
                    endpoint=endpoint,
                    database_name=database,
                    key=key,
                    allow_insecure_http=environment.is_local,
                )
            except (TypeError, ValueError) as error:
                raise AlarmDeliveryConnectionsError(
                    f'Connection {declaration.connection_ref} is invalid'
                ) from error
        return MappingProxyType(resolved)


# La ausencia deshabilita Delivery. Un archivo presente e incorrecto falla explícitamente.
def read_connection_registry(process_root: Path) -> AlarmDeliveryConnectionRegistry | None:
    if not isinstance(process_root, Path):
        raise TypeError('process_root must be a Path')
    filename = process_root / _FILE
    if not filename.exists() and not filename.is_symlink():
        return None
    if filename.is_symlink() or not filename.is_file():
        raise AlarmDeliveryConnectionsError('Connections file must be a regular file')
    try:
        if filename.stat().st_size > _MAX_FILE_BYTES:
            raise AlarmDeliveryConnectionsError('Connections file is too large')
        document = json.loads(filename.read_text(encoding='utf-8'), object_pairs_hook=_unique_keys)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AlarmDeliveryConnectionsError('Connections file could not be read') from error
    if (
        not isinstance(document, dict)
        or set(document) != {'schema_version', 'connections'}
        or type(document['schema_version']) is not int
        or document['schema_version'] != 1
        or not isinstance(document['connections'], dict)
        or not document['connections']
    ):
        raise AlarmDeliveryConnectionsError('Connections document is invalid')
    definitions: list[CosmosConnectionDeclaration] = []
    variables: dict[str, str] = {}
    for ref, item in sorted(document['connections'].items()):
        if (
            not isinstance(ref, str)
            or _REF.fullmatch(ref) is None
            or not isinstance(item, dict)
            or set(item) != _FIELDS
        ):
            raise AlarmDeliveryConnectionsError('Connections document contains an invalid reference')
        for field in _FIELDS:
            variable = item[field]
            if not isinstance(variable, str) or _VARIABLE.fullmatch(variable) is None:
                raise AlarmDeliveryConnectionsError(
                    f'Connection {ref} has an invalid variable declaration'
                )
            previous = variables.setdefault(variable, field)
            if previous != field:
                raise AlarmDeliveryConnectionsError(
                    'The same variable cannot have different connection roles'
                )
        if len(set(item.values())) != len(_FIELDS):
            raise AlarmDeliveryConnectionsError(f'Connection {ref} reuses a variable')
        definitions.append(CosmosConnectionDeclaration(connection_ref=ref, **item))
    return AlarmDeliveryConnectionRegistry(declarations=tuple(definitions))


# Evita que JSON oculte referencias repetidas al usar la última declaración.
def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AlarmDeliveryConnectionsError('Connections document has duplicate keys')
        result[key] = value
    return result
