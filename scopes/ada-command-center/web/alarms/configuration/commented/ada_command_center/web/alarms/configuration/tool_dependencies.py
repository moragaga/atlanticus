from __future__ import annotations

from copy import deepcopy

from ada_command_center.domain.alarms import AlarmConfiguration
from ada_command_center.domain.tools import ToolDependencyManifest
from ada_command_center.web.alarms.configuration.errors import (
    AlarmConfigurationToolDependencyError,
)

# Metadata exclusiva del workspace; AlarmConfiguration continúa siendo rules/messages puros.
WORKSPACE_TOOL_CATALOG_REVISION_KEY = '_confirmed_tool_catalog_revision'


# Cada guardado del draft fija la revisión Tools que debe validar y publicar ese workspace.
def pin_workspace_tool_catalog_revision(
    payload: dict[str, object],
    catalog_revision: str,
) -> dict[str, object]:
    revision = _require_revision(catalog_revision)
    pinned = deepcopy(payload)
    pinned[WORKSPACE_TOOL_CATALOG_REVISION_KEY] = revision
    return pinned


def require_workspace_tool_catalog_revision(payload: dict[str, object]) -> str:
    try:
        return _require_revision(payload[WORKSPACE_TOOL_CATALOG_REVISION_KEY])
    except KeyError as error:
        raise AlarmConfigurationToolDependencyError(
            'Alarm Configuration draft is not pinned to a Confirmed Tool Catalog revision'
        ) from error


# Selecciona sólo las Tools realmente referenciadas, pero conserva la revisión
# del catálogo completo.
def select_alarm_tool_dependencies(
    configuration: AlarmConfiguration,
    confirmed_catalog: ToolDependencyManifest,
) -> ToolDependencyManifest:
    if not isinstance(configuration, AlarmConfiguration):
        raise TypeError('configuration must be an AlarmConfiguration')
    if not isinstance(confirmed_catalog, ToolDependencyManifest):
        raise TypeError('confirmed_catalog must be a ToolDependencyManifest')
    selected = []
    for tool_key in _referenced_tool_keys(configuration):
        entry = confirmed_catalog.get(tool_key)
        if entry is None:
            raise AlarmConfigurationToolDependencyError(
                f'Alarm Configuration references unknown confirmed Tool {tool_key!r}'
            )
        selected.append(entry)
    return ToolDependencyManifest(
        confirmed_tool_catalog_revision=confirmed_catalog.revision,
        tools=tuple(selected),
    )


def _referenced_tool_keys(configuration: AlarmConfiguration) -> tuple[str, ...]:
    keys: set[str] = set()
    # No se filtran Rules ni escalation steps deshabilitados: B.2 también califica sus referencias.
    for rule in configuration.rules:
        keys.add(rule.escalation.origin_tool_key)
        keys.update(step.target_tool_key for step in rule.escalation.steps)
        keys.update(target.tool_key for target in rule.visual_targets)
    return tuple(sorted(keys))


def _require_revision(value: object) -> str:
    if not isinstance(value, str):
        raise AlarmConfigurationToolDependencyError(
            'Confirmed Tool Catalog revision must be text'
        )
    normalized = value.strip()
    if not normalized or normalized != value:
        raise AlarmConfigurationToolDependencyError(
            'Confirmed Tool Catalog revision has an invalid format'
        )
    return normalized
