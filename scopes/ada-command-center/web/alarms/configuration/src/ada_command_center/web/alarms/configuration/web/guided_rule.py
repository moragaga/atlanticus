from __future__ import annotations

from collections.abc import Mapping

from dash import html

from ada_command_center.web.alarms.configuration.web.ids import (
    RULE_SECTION_TYPE,
)

RULE_SECTIONS = (
    ('general', 'Información general', 'Identidad, clasificación y textos de presentación.'),
    ('evaluation', 'Evaluación y prioridad', 'Evaluador, parámetros y orden del grupo.'),
    ('behavior', 'Comportamiento', 'Reaparición, desactivación y origen operacional.'),
    ('visual', 'Presentación visual', 'Elementos y componentes que la Web debe representar.'),
)


def build_rule_section(
    children: list[object],
    *,
    section: str,
    criticality: object,
    targets: list[object],
    references: dict[str, object] | None,
    deactivation_enabled: object = None,
) -> object:
    selected = section if section in {item[0] for item in RULE_SECTIONS} else 'general'
    index = next(i for i, item in enumerate(RULE_SECTIONS) if item[0] == selected)
    _, label, help_text = RULE_SECTIONS[index]
    deactivation = children[6]
    if deactivation_enabled is False:
        deactivation = html.Fieldset(deactivation.children[:2], className='alarm-guided__group')
    escalation = children[7]
    if criticality == 'C3':
        escalation = _criticality_three_panel(escalation)
    panels = {
        'general': [children[2], children[3]],
        'evaluation': [children[4]],
        'behavior': [children[5], deactivation, escalation],
        'visual': [_visual_panel(children[8], targets, references)],
    }
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Strong(children[0].children),
                            html.Small(
                                'Los cambios permanecen en edición hasta guardar el borrador.'
                            ),
                        ],
                        className='alarm-guided__heading',
                    ),
                    children[1],
                ],
                className='alarm-guided__top',
            ),
            html.Div(
                [
                    html.Nav(
                        [
                            html.Button(
                                [
                                    html.Span(
                                        f'{position + 1:02d}', className='alarm-guided__step-number'
                                    ),
                                    html.Span(item_label),
                                ],
                                id={'type': RULE_SECTION_TYPE, 'section': key},
                                n_clicks=0,
                                type='button',
                                className='alarm-guided__tab alarm-guided__tab--active'
                                if key == selected
                                else 'alarm-guided__tab',
                                **{'aria-current': 'step' if key == selected else 'false'},
                            )
                            for position, (key, item_label, _) in enumerate(RULE_SECTIONS)
                        ],
                        className='alarm-guided__tabs',
                        **{'aria-label': 'Apartados de la regla'},
                    ),
                    html.Section(
                        [
                            html.Div(
                                [
                                    html.Span(f'Apartado {index + 1} de {len(RULE_SECTIONS)}'),
                                    html.H5(label),
                                    html.P(help_text),
                                ],
                                className='alarm-guided__section-heading',
                            ),
                            html.Div(panels[selected], className='alarm-guided__panels'),
                        ],
                        className='alarm-guided__content',
                    ),
                ],
                className='alarm-guided__body',
            ),
        ],
        className='alarm-guided',
    )


def _criticality_three_panel(panel: object) -> object:
    children = getattr(panel, 'children', None)
    if not isinstance(children, list):
        return panel
    existing = [child for child in children[3:] if child is not None]
    return html.Section(
        [
            html.H5('Origen operacional'),
            children[1],
            html.P(
                'C3 no tiene escalonamiento. El origen conserva su función de referencia.',
                className='alarm-guided__notice',
            ),
            *(
                [
                    html.P(
                        'Existen pasos anteriores que deben revisarse y eliminarse para C3.',
                        className='alarm-guided__notice',
                    ),
                    *existing,
                ]
                if existing
                else []
            ),
        ],
        className='alarm-guided__conditional',
    )


def _visual_panel(
    panel: object,
    targets: list[object],
    references: dict[str, object] | None,
) -> object:
    children = getattr(panel, 'children', None)
    if not isinstance(children, list):
        return panel
    result = []
    target_index = 0
    for child in children:
        if child.__class__.__name__ != 'Fieldset':
            result.append(child)
            continue
        raw = targets[target_index] if target_index < len(targets) else None
        target_index += 1
        data = raw if isinstance(raw, dict) else {}
        kind = tool_kind(references, data.get('tool_key'))
        inner = getattr(child, 'children', None)
        if not isinstance(inner, list):
            result.append(child)
            continue
        if kind == 'INTEGRATED_OPERATIONS' and data.get('process_projection_mode') is None:
            contents = [item for item in inner if not _is_process_mode_control(item)]
            result.append(
                html.Fieldset(
                    [
                        *contents[:3],
                        html.P(
                            'Operaciones Integradas usa posiciones Mina/Planta y no requiere modo Process.',
                            className='alarm-guided__tip',
                        ),
                        *contents[3:],
                    ],
                    className='alarm-guided__target',
                )
            )
        else:
            tip = (
                'Process utiliza carrusel. Genérico o distribuido determina su agrupación.'
                if kind == 'PROCESS'
                else 'Selecciona una herramienta del catálogo para comprobar sus requisitos.'
                if kind is None
                else 'El modo Process no corresponde a Operaciones Integradas: elimínalo.'
            )
            result.append(
                html.Fieldset(
                    [*inner[:3], html.P(tip, className='alarm-guided__tip'), *inner[3:]],
                    className='alarm-guided__target',
                )
            )
    return html.Section(result, className='alarm-guided__visual')


def _is_process_mode_control(value: object) -> bool:
    children = getattr(value, 'children', None)
    if not isinstance(children, list):
        return False
    for child in children:
        component_id = getattr(child, 'id', None)
        if (
            isinstance(component_id, dict)
            and component_id.get('field') == 'process_projection_mode'
        ):
            return True
    return False


def tool_kind(references: Mapping[str, object] | None, tool_key: object) -> str | None:
    if not isinstance(references, Mapping) or not isinstance(tool_key, str):
        return None
    items = references.get('tools')
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get('tool_key') == tool_key:
            kind = item.get('kind')
            return kind if isinstance(kind, str) else None
    return None
