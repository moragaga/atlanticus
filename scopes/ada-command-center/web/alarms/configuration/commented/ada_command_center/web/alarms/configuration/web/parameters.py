# Las etiquetas del formulario se separan de los tipos TEXT, FLOAT y BOOLEAN del documento.
# Estructura y comportamiento idénticos al módulo productivo.

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from dash import dcc, html

from ada_command_center.web.alarms.configuration.web.authoring import (
    normalize_authoring_document,
)
from ada_command_center.web.alarms.configuration.web.ids import (
    PARAMETER_ADD_TYPE,
    PARAMETER_FIELD_TYPE,
    PARAMETER_REMOVE_TYPE,
)
from ada_command_center.web.alarms.configuration.web.select_style import dash_select_style

PARAMETER_KINDS = ('TEXT', 'FLOAT', 'BOOLEAN')


def parameter_rows(rule: Mapping[str, object]) -> list[dict[str, object]]:
    prepared = rule.get('_parameter_rows')
    if isinstance(prepared, list):
        return [deepcopy(row) for row in prepared if isinstance(row, dict)]
    raw = rule.get('parameters')
    if not isinstance(raw, Mapping):
        return []
    result = []
    for key, value in raw.items():
        if type(value) is bool:
            kind = 'BOOLEAN'
        elif isinstance(value, (float, int)) and not isinstance(value, bool):
            kind = 'FLOAT'
            value = float(value)
        else:
            kind = 'TEXT'
        result.append({'key': key, 'kind': kind, 'value': value})
    return result


def parameter_issues(rule: Mapping[str, object]) -> tuple[str, ...]:
    prepared = rule.get('_parameter_rows')
    if not isinstance(prepared, list):
        return ()
    seen: set[str] = set()
    issues: list[str] = []
    for number, row in enumerate(prepared, start=1):
        if not isinstance(row, dict):
            issues.append(f'Parámetro {number}: estructura no reconocida.')
            continue
        key = row.get('key')
        kind = row.get('kind')
        value = row.get('value')
        if not isinstance(key, str) or not key.strip() or key != key.strip():
            issues.append(f'Parámetro {number}: indica un nombre técnico sin espacios externos.')
        elif key in seen:
            issues.append(f'Parámetro {number}: el nombre está repetido.')
        else:
            seen.add(key)
        if kind not in PARAMETER_KINDS:
            issues.append(f'Parámetro {number}: selecciona un tipo válido.')
        elif kind == 'TEXT' and not isinstance(value, str):
            issues.append(f'Parámetro {number}: indica un texto.')
        elif kind == 'FLOAT' and (type(value) not in (int, float)):
            issues.append(f'Parámetro {number}: indica un número.')
        elif kind == 'BOOLEAN' and type(value) is not bool:
            issues.append(f'Parámetro {number}: indica verdadero o falso.')
    return tuple(issues)


def _rule(document: dict[str, object], rule_index: int) -> dict[str, object]:
    rules = document.get('rules')
    if not isinstance(rules, list) or type(rule_index) is not int:
        raise ValueError('Invalid Alarm Configuration rule')
    rule = rules[rule_index]
    if not isinstance(rule, dict):
        raise ValueError('Invalid Alarm Configuration rule')
    return rule


def _prepare(
    document: dict[str, object], rule_index: int
) -> tuple[dict[str, object], dict[str, object], list[dict[str, object]]]:
    updated = normalize_authoring_document(document)
    rule = _rule(updated, rule_index)
    rows = parameter_rows(rule)
    rule['_parameter_rows'] = rows
    return updated, rule, rows


def _synchronize(rule: dict[str, object], rows: list[dict[str, object]]) -> None:
    parameters: dict[str, str | float | bool] = {}
    for row in rows:
        key = row.get('key')
        kind = row.get('kind')
        value = row.get('value')
        if not isinstance(key, str) or not key.strip() or key != key.strip() or key in parameters:
            continue
        if kind == 'TEXT' and isinstance(value, str) or kind == 'BOOLEAN' and type(value) is bool:
            parameters[key] = value
        elif kind == 'FLOAT' and type(value) in (int, float):
            parameters[key] = float(value)
    rule['parameters'] = parameters


def add_parameter(document: dict[str, object], rule_index: int) -> dict[str, object]:
    updated, rule, rows = _prepare(document, rule_index)
    rows.append({'key': '', 'kind': 'TEXT', 'value': ''})
    _synchronize(rule, rows)
    return updated


def remove_parameter(
    document: dict[str, object], rule_index: int, row_index: int
) -> dict[str, object]:
    updated, rule, rows = _prepare(document, rule_index)
    del rows[row_index]
    _synchronize(rule, rows)
    return updated


def set_parameter_field(
    document: dict[str, object], rule_index: int, row_index: int, field: str, value: object
) -> dict[str, object]:
    if field not in {'key', 'kind', 'value'}:
        raise ValueError('Unsupported parameter field')
    updated, rule, rows = _prepare(document, rule_index)
    row = rows[row_index]
    if field == 'key':
        row['key'] = value
    elif field == 'kind':
        if value not in PARAMETER_KINDS:
            raise ValueError('Unsupported parameter kind')
        row['kind'] = value
        row['value'] = {'TEXT': '', 'FLOAT': None, 'BOOLEAN': None}[value]
    elif field == 'value':
        kind = row.get('kind')
        if kind == 'FLOAT' and type(value) in (int, float):
            row['value'] = float(value)
        else:
            row['value'] = value
    _synchronize(rule, rows)
    return updated


def parameter_editor(rule_index: int, rule: dict[str, object]) -> object:
    rows = parameter_rows(rule)
    items = []
    for index, row in enumerate(rows):
        kind = row.get('kind')
        value = row.get('value')
        value_id = {
            'type': PARAMETER_FIELD_TYPE,
            'rule': rule_index,
            'parameter': index,
            'field': 'value',
        }
        if kind == 'FLOAT':
            value_field = dcc.Input(
                id=value_id,
                type='number',
                value=value,
                debounce=True,
                className='alarm-parameter__value',
            )
        elif kind == 'BOOLEAN':
            value_field = dcc.RadioItems(
                id=value_id,
                options=[{'label': 'Sí', 'value': True}, {'label': 'No', 'value': False}],
                value=value,
                className='alarm-admin__choices',
            )
        else:
            value_field = dcc.Input(
                id=value_id,
                type='text',
                value=value if isinstance(value, str) else '',
                debounce=True,
                className='alarm-parameter__value',
            )
        items.append(
            html.Div(
                [
                    html.Label(
                        [
                            html.Span('Nombre del parámetro'),
                            dcc.Input(
                                id={
                                    'type': PARAMETER_FIELD_TYPE,
                                    'rule': rule_index,
                                    'parameter': index,
                                    'field': 'key',
                                },
                                type='text',
                                value=row.get('key', ''),
                                debounce=True,
                                placeholder='Nombre exigido por el evaluador',
                            ),
                        ],
                        className='alarm-guided__field',
                    ),
                    html.Label(
                        [
                            html.Span('Tipo'),
                            html.Div(
                                dcc.Dropdown(
                                    id={
                                        'type': PARAMETER_FIELD_TYPE,
                                        'rule': rule_index,
                                        'parameter': index,
                                        'field': 'kind',
                                    },
                                    options=[
                                        {'label': 'Text', 'value': 'TEXT'},
                                        {'label': 'Float', 'value': 'FLOAT'},
                                        {'label': 'Boolean', 'value': 'BOOLEAN'},
                                    ],
                                    value=kind,
                                    clearable=False,
                                    searchable=False,
                                    style=dash_select_style(),
                                    className='alarm-admin__dropdown',
                                ),
                                className='alarm-admin__dropdown-shell',
                            ),
                        ],
                        className='alarm-guided__field',
                    ),
                    html.Label([html.Span('Valor'), value_field], className='alarm-guided__field'),
                    html.Button(
                        'Quitar',
                        id={'type': PARAMETER_REMOVE_TYPE, 'rule': rule_index, 'parameter': index},
                        n_clicks=0,
                        type='button',
                        className='btn btn-outline-danger btn-sm',
                    ),
                ],
                className='alarm-parameter__row',
            )
        )
    errors = parameter_issues(rule)
    return html.Section(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.H5('Parámetros del evaluador'),
                            html.P(
                                'Agrega los valores exigidos por el evaluador. No necesitas escribir JSON.'
                            ),
                        ]
                    ),
                    html.Button(
                        '+ Agregar parámetro',
                        id={'type': PARAMETER_ADD_TYPE, 'rule': rule_index},
                        type='button',
                        n_clicks=0,
                        className='btn btn-outline-secondary btn-sm',
                    ),
                ],
                className='alarm-parameter__heading',
            ),
            html.Div(items, className='alarm-parameter__rows'),
            html.Ul([html.Li(error) for error in errors], className='alarm-parameter__issues')
            if errors
            else None,
        ],
        className='alarm-parameter',
    )
