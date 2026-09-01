from __future__ import annotations

# Traduce tablas Web a ToolStructure y delega todas las reglas estructurales al dominio.
import re
from collections.abc import Iterable, Mapping
from typing import Any

from ada.configuration.tools import (
    ToolConfiguration,
    ToolStructure,
)

_SPLIT_KEYS = re.compile(r'[,\n]')


class ToolStructureEditorValidationError(ValueError):
    pass


def structure_editor_table_data_from_configuration(
    configuration: ToolConfiguration,
) -> tuple[list[dict[str, object]], list[dict[str, object]], str | None]:
    structure = configuration.structure
    if structure is None:
        return [], [], None
    components: list[dict[str, object]] = []
    subcomponents: list[dict[str, object]] = []
    for component in structure.components:
        components.append(
            {
                'key': component.key,
                'display_name': component.display_name,
                'scope': component.scope.value if component.scope is not None else None,
                'layout_role': (
                    component.layout_role.value if component.layout_role is not None else None
                ),
            }
        )
        for subcomponent in component.subcomponents:
            subcomponents.append(
                {
                    'owner_component_key': component.key,
                    'key': subcomponent.key,
                    'display_name': subcomponent.display_name,
                    'linked_component_keys': ', '.join(subcomponent.linked_component_keys),
                }
            )
    operational_scope = (
        structure.operational_scope.value if structure.operational_scope is not None else None
    )
    return components, subcomponents, operational_scope


def build_structure_from_editor_tables(
    *,
    base_configuration: ToolConfiguration,
    component_rows: Iterable[Mapping[str, Any]] | None,
    subcomponent_rows: Iterable[Mapping[str, Any]] | None,
    operational_scope: object,
) -> ToolStructure:
    components = _rows(component_rows, label='Tool component rows')
    subcomponents = _rows(subcomponent_rows, label='Tool subcomponent rows')
    component_keys = tuple(_text(row.get('key')) for row in components)
    if len(component_keys) != len(set(component_keys)):
        raise ToolStructureEditorValidationError(
            'Tool Structure component keys must be unique before assigning subcomponents'
        )
    grouped: dict[str, list[dict[str, object]]] = {key: [] for key in component_keys}
    for row in subcomponents:
        owner_key = _text(row.get('owner_component_key'))
        if owner_key not in grouped:
            raise ToolStructureEditorValidationError(
                f'Tool subcomponent owner component does not exist: {owner_key!r}'
            )
        grouped[owner_key].append(
            {
                'key': _text(row.get('key')),
                'display_name': _text(row.get('display_name')),
                'linked_component_keys': list(
                    _linked_component_keys(row.get('linked_component_keys'))
                ),
            }
        )
    document = {
        'tool_key': base_configuration.tool_key,
        'kind': base_configuration.kind.value,
        'operational_scope': _optional_text(operational_scope),
        'components': [
            {
                'key': key,
                'display_name': _text(row.get('display_name')),
                'scope': _optional_text(row.get('scope')),
                'layout_role': _optional_text(row.get('layout_role')),
                'subcomponents': grouped[key],
            }
            for key, row in zip(component_keys, components, strict=True)
        ],
    }
    try:
        return ToolStructure.from_document(document)
    except ValueError as error:
        raise ToolStructureEditorValidationError(str(error)) from error


def build_configuration_from_structure_editor(
    *,
    base_configuration: ToolConfiguration,
    structure_document: Mapping[str, Any],
) -> ToolConfiguration:
    try:
        structure = ToolStructure.from_document(structure_document)
        return ToolConfiguration(
            tool_key=base_configuration.tool_key,
            display_name=base_configuration.display_name,
            kind=base_configuration.kind,
            source_consumption=base_configuration.source_consumption,
            source_operational_participation=base_configuration.source_operational_participation,
            structure=structure,
        )
    except ValueError as error:
        raise ToolStructureEditorValidationError(str(error)) from error


def _rows(
    value: Iterable[Mapping[str, Any]] | None,
    *,
    label: str,
) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)):
        raise ToolStructureEditorValidationError(f'{label} must be a collection')
    try:
        rows = tuple(value)
    except TypeError as error:
        raise ToolStructureEditorValidationError(f'{label} must be a collection') from error
    if not all(isinstance(row, Mapping) for row in rows):
        raise ToolStructureEditorValidationError(f'{label} must contain mappings')
    return rows


def _linked_component_keys(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(item.strip() for item in _SPLIT_KEYS.split(value) if item.strip())
    if isinstance(value, (bytes, Mapping)):
        raise ToolStructureEditorValidationError(
            'Tool linked component keys must be text or a collection'
        )
    try:
        items = tuple(value)
    except TypeError as error:
        raise ToolStructureEditorValidationError(
            'Tool linked component keys must be text or a collection'
        ) from error
    if not all(isinstance(item, str) for item in items):
        raise ToolStructureEditorValidationError('Tool linked component keys must contain strings')
    return tuple(item.strip() for item in items if item.strip())


def _text(value: object) -> str:
    if value is None:
        return ''
    if not isinstance(value, str):
        return str(value).strip()
    return value.strip()


def _optional_text(value: object) -> str | None:
    text = _text(value)
    return text or None
