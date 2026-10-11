from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from atlanticus.configuration import ConfigurationVariableSpec
from atlanticus.connectivity.cosmos import CosmosSettings
from atlanticus.kernel import Environment

_VARIABLE = re.compile(r'[A-Z][A-Z0-9_]*\Z')
_TOOL = re.compile(r'[a-z][a-z0-9_-]{0,63}\Z')
_FILE = 'config/connections.json'
_FIELDS = frozenset({'endpoint_var', 'database_var', 'credential_var'})


class AlarmDeliveryConnectionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ToolConnection:
    tool_key: str
    endpoint_var: str
    database_var: str
    credential_var: str


@dataclass(frozen=True, slots=True)
class ToolConnectionRegistry:
    declarations: tuple[ToolConnection, ...]

    def specs(self) -> tuple[ConfigurationVariableSpec, ...]:
        names: dict[str, bool] = {}
        for item in self.declarations:
            for key, sensitive in (
                (item.endpoint_var, False),
                (item.database_var, False),
                (item.credential_var, True),
            ):
                names[key] = names.get(key, False) or sensitive
        return tuple(
            ConfigurationVariableSpec(key=key, sensitive=sensitive)
            for key, sensitive in sorted(names.items())
        )

    def resolve(
        self, *, values: Mapping[str, str], environment: Environment
    ) -> dict[str, CosmosSettings]:
        connections: dict[str, CosmosSettings] = {}
        for item in self.declarations:
            try:
                connections[item.tool_key] = CosmosSettings(
                    endpoint=values[item.endpoint_var],
                    database_name=values[item.database_var],
                    key=values[item.credential_var],
                    allow_insecure_http=environment.is_local,
                )
            except (KeyError, TypeError, ValueError) as error:
                raise AlarmDeliveryConnectionError(
                    f'Tool {item.tool_key} has an invalid Cosmos destination'
                ) from error
        destinations = [(value.endpoint, value.database_name) for value in connections.values()]
        if len(set(destinations)) != len(destinations):
            raise AlarmDeliveryConnectionError('Each Tool must have its own Cosmos database')
        return connections


def read_connection_registry(root: Path) -> ToolConnectionRegistry:
    if not isinstance(root, Path):
        raise TypeError('Configuration root must be a Path')
    path = root / _FILE
    if path.is_symlink() or not path.is_file():
        raise AlarmDeliveryConnectionError('Delivery connections.json is required')
    if path.stat().st_size > 65536:
        raise AlarmDeliveryConnectionError('Delivery connections.json is too large')
    try:
        document = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_no_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AlarmDeliveryConnectionError('Delivery connections.json is invalid') from error
    if (
        not isinstance(document, dict)
        or set(document) != {'schema_version', 'connections'}
        or type(document['schema_version']) is not int
        or document['schema_version'] != 1
        or not isinstance(document['connections'], dict)
        or not document['connections']
    ):
        raise AlarmDeliveryConnectionError('Delivery connection registry schema is invalid')
    declarations = []
    roles: dict[str, str] = {}
    for key, item in sorted(document['connections'].items()):
        if (
            not isinstance(key, str)
            or _TOOL.fullmatch(key) is None
            or not isinstance(item, dict)
            or set(item) != _FIELDS
        ):
            raise AlarmDeliveryConnectionError('Invalid Tool connection declaration')
        for role in _FIELDS:
            variable = item[role]
            if not isinstance(variable, str) or _VARIABLE.fullmatch(variable) is None:
                raise AlarmDeliveryConnectionError('Invalid Cosmos variable declaration')
            previous = roles.setdefault(variable, role)
            if previous != role:
                raise AlarmDeliveryConnectionError('Cosmos variable roles must not overlap')
        if len(set(item.values())) != 3:
            raise AlarmDeliveryConnectionError('Tool connection variables must be distinct')
        declarations.append(
            ToolConnection(key, item['endpoint_var'], item['database_var'], item['credential_var'])
        )
    return ToolConnectionRegistry(tuple(declarations))


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, val in pairs:
        if key in result:
            raise AlarmDeliveryConnectionError('Duplicate key in Delivery connections.json')
        result[key] = val
    return result
