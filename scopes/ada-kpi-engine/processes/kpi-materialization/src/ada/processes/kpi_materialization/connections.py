from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from ada.kpis.materialization import require_tool_key
from ada.processes.kpi_materialization.errors import KpiMaterializationConnectionsError
from atlanticus.configuration import ConfigurationVariableSpec
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.kernel import Environment

_VARIABLE = re.compile(r'[A-Z][A-Z0-9_]*\Z')
_MAX_FILE_BYTES = 65536
_FILE = Path('config/connections.json')
_FIELDS = frozenset({'endpoint_var', 'database_var', 'credential_var'})


@dataclass(frozen=True, slots=True)
class CosmosConnectionDeclaration:
    tool_key: str
    endpoint_var: str
    database_var: str
    credential_var: str


@dataclass(frozen=True, slots=True)
class KpiMaterializationConnectionRegistry:
    declarations: tuple[CosmosConnectionDeclaration, ...]

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
                raise KpiMaterializationConnectionsError(
                    f'Connection for {declaration.tool_key} has an unresolved variable'
                ) from error
            try:
                resolved[declaration.tool_key] = CosmosSettings(
                    endpoint=endpoint,
                    database_name=database,
                    key=key,
                    allow_insecure_http=environment.is_local,
                )
            except (TypeError, ValueError) as error:
                raise KpiMaterializationConnectionsError(
                    f'Connection for {declaration.tool_key} is invalid'
                ) from error
        return MappingProxyType(resolved)


def read_connection_registry(process_root: Path) -> KpiMaterializationConnectionRegistry:
    if not isinstance(process_root, Path):
        raise TypeError('process_root must be a Path')
    filename = process_root / _FILE
    if not filename.exists() and not filename.is_symlink():
        raise KpiMaterializationConnectionsError('Connections file is required')
    if filename.is_symlink() or not filename.is_file():
        raise KpiMaterializationConnectionsError('Connections file must be a regular file')
    try:
        if filename.stat().st_size > _MAX_FILE_BYTES:
            raise KpiMaterializationConnectionsError('Connections file is too large')
        document = json.loads(
            filename.read_text(encoding='utf-8'),
            object_pairs_hook=_unique_keys,
        )
    except KpiMaterializationConnectionsError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise KpiMaterializationConnectionsError('Connections file could not be read') from error
    if (
        not isinstance(document, dict)
        or set(document) != {'schema_version', 'connections'}
        or type(document['schema_version']) is not int
        or document['schema_version'] != 1
        or not isinstance(document['connections'], dict)
        or not document['connections']
    ):
        raise KpiMaterializationConnectionsError('Connections document is invalid')
    declarations: list[CosmosConnectionDeclaration] = []
    variables: dict[str, str] = {}
    for tool_key, item in sorted(document['connections'].items()):
        try:
            resolved_tool_key = require_tool_key(tool_key)
        except ValueError as error:
            raise KpiMaterializationConnectionsError(
                'Connections document contains an invalid tool_key'
            ) from error
        if not isinstance(item, dict) or set(item) != _FIELDS:
            raise KpiMaterializationConnectionsError(
                f'Connection for {resolved_tool_key} is invalid'
            )
        for field in _FIELDS:
            variable = item[field]
            if not isinstance(variable, str) or _VARIABLE.fullmatch(variable) is None:
                raise KpiMaterializationConnectionsError(
                    f'Connection for {resolved_tool_key} has an invalid variable declaration'
                )
            previous = variables.setdefault(variable, field)
            if previous != field:
                raise KpiMaterializationConnectionsError(
                    'The same variable cannot have different connection roles'
                )
        if len(set(item.values())) != len(_FIELDS):
            raise KpiMaterializationConnectionsError(
                f'Connection for {resolved_tool_key} reuses a variable'
            )
        declarations.append(CosmosConnectionDeclaration(tool_key=resolved_tool_key, **item))
    return KpiMaterializationConnectionRegistry(declarations=tuple(declarations))


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise KpiMaterializationConnectionsError('Connections document has duplicate keys')
        result[key] = value
    return result
