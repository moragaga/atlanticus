# Espejo pedagógico en español del archivo productivo equivalente.
# Delivery usa tool_key como identidad de conexión y un contenedor Cosmos fijo.
# No existe una segunda configuración de targets porque no agrega variación real.

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

_TOOL_KEY = re.compile(r'[a-z][a-z0-9_-]{0,63}\Z')
_VARIABLE = re.compile(r'[A-Z][A-Z0-9_]*\Z')
_MAX_FILE_BYTES = 65536
_FILE = Path('config/connections.json')
_FIELDS = frozenset({'endpoint_var', 'database_var', 'credential_var'})


class AlarmDeliveryConnectionsError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CosmosToolConnectionDeclaration:
    tool_key: str
    endpoint_var: str
    database_var: str
    credential_var: str


@dataclass(frozen=True, slots=True)
class AlarmDeliveryConnectionRegistry:
    declarations: tuple[CosmosToolConnectionDeclaration, ...]

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

    def resolve(
        self,
        *,
        values: Mapping[str, str],
        environment: Environment,
    ) -> Mapping[str, CosmosSettings]:
        resolved: dict[str, CosmosSettings] = {}
        for declaration in self.declarations:
            try:
                endpoint = values[declaration.endpoint_var]
                database = values[declaration.database_var]
                key = values[declaration.credential_var]
            except KeyError as error:
                raise AlarmDeliveryConnectionsError(
                    f'Tool {declaration.tool_key} has an unresolved Cosmos variable'
                ) from error
            try:
                resolved[declaration.tool_key] = CosmosSettings(
                    endpoint=endpoint,
                    database_name=database,
                    key=key,
                    allow_insecure_http=environment.is_local,
                )
            except (TypeError, ValueError) as error:
                raise AlarmDeliveryConnectionsError(
                    f'Tool {declaration.tool_key} has an invalid Cosmos connection'
                ) from error
        return MappingProxyType(resolved)


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
        document = json.loads(
            filename.read_text(encoding='utf-8'),
            object_pairs_hook=_unique_keys,
        )
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
    definitions: list[CosmosToolConnectionDeclaration] = []
    variables: dict[str, str] = {}
    for tool_key, item in sorted(document['connections'].items()):
        if (
            not isinstance(tool_key, str)
            or _TOOL_KEY.fullmatch(tool_key) is None
            or not isinstance(item, dict)
            or set(item) != _FIELDS
        ):
            raise AlarmDeliveryConnectionsError(
                'Connections document contains an invalid Tool connection'
            )
        for field in _FIELDS:
            variable = item[field]
            if not isinstance(variable, str) or _VARIABLE.fullmatch(variable) is None:
                raise AlarmDeliveryConnectionsError(
                    f'Tool {tool_key} has an invalid variable declaration'
                )
            previous = variables.setdefault(variable, field)
            if previous != field:
                raise AlarmDeliveryConnectionsError(
                    'The same variable cannot have different connection roles'
                )
        if len(set(item.values())) != len(_FIELDS):
            raise AlarmDeliveryConnectionsError(f'Tool {tool_key} reuses a variable')
        definitions.append(
            CosmosToolConnectionDeclaration(
                tool_key=tool_key,
                endpoint_var=item['endpoint_var'],
                database_var=item['database_var'],
                credential_var=item['credential_var'],
            )
        )
    return AlarmDeliveryConnectionRegistry(declarations=tuple(definitions))


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise AlarmDeliveryConnectionsError('Connections document has duplicate keys')
        result[key] = value
    return result
