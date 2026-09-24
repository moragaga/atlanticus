from __future__ import annotations

from collections.abc import Mapping

from dash import html

from ada_command_center.web.alarms.configuration.web.ids import (
    RULE_SECTION_TYPE,
    STEP_ADD_TYPE,
)

RULE_SECTIONS = (
    ('general', 'Información general', 'Identidad, nombre visible y texto que explica la alarma.'),
    ('classification', 'Clasificación', 'Define el comportamiento y las categorías de esta regla.'),
    (
        'evaluation',
        'Evaluación y prioridad',
        'Indica cómo se evalúa y cómo compite con otras reglas.',
    ),
    (
        'reappearance',
        'Reaparición',
        'Opcional: cuándo puede volver una alarma previamente gestionada.',
    ),
    ('deactivation', 'Desactivación', 'Configura si se permite una desactivación temporal.'),
    (
        'escalation',
        'Origen y escalamiento',
        'El escalamiento no es lo mismo que el destino visual.',
    ),
    ('visual', 'Visualización', 'Herramientas y elementos que la Web debe representar o colorear.'),
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
    active = children[index + 2]
    if selected == 'deactivation' and deactivation_enabled is False:
        active = html.Fieldset(active.children[:2], className='alarm-guided__group')
    if selected == 'escalation' and criticality == 'C3':
        active = _criticality_three_panel(active)
    if selected == 'visual':
        active = _visual_panel(active, targets, references)
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Strong(children[0].children),
                            html.Small(
                                'Completa cada sección. Los cambios se conservan en el editor.'
                            ),
                        ],
                        className='alarm-guided__heading',
                    ),
                    children[1],
                ],
                className='alarm-guided__top',
            ),
            html.Nav(
                [
                    html.Button(
                        [html.Span(f'{position + 1:02d}'), html.Span(item_label)],
                        id={'type': RULE_SECTION_TYPE, 'section': key},
                        n_clicks=0,
                        type='button',
                        className=(
                            'alarm-guided__tab alarm-guided__tab--active'
                            if key == selected
                            else 'alarm-guided__tab'
                        ),
                        **{'aria-current': 'step' if key == selected else 'false'},
                    )
                    for position, (key, item_label, _) in enumerate(RULE_SECTIONS)
                ],
                className='alarm-guided__tabs',
                **{'aria-label': 'Secciones de la alarma'},
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.Span(f'Sección {index + 1} de {len(RULE_SECTIONS)}'),
                            html.H5(label),
                            html.P(help_text),
                        ],
                        className='alarm-guided__section-heading',
                    ),
                    active,
                ],
                className='alarm-guided__content',
            ),
        ],
        className='alarm-guided',
    )


def _criticality_three_panel(panel: object) -> object:
    children = getattr(panel, 'children', None)
    if not isinstance(children, list):
        return panel
    kept = []
    for child in children:
        component_id = getattr(child, 'id', None)
        if isinstance(component_id, dict) and component_id.get('type') == STEP_ADD_TYPE:
            continue
        kept.append(child)
    return html.Section(
        [
            html.P(
                'C3 utiliza solamente la herramienta de origen. No admite nuevos pasos '
                'habilitados. Si hay pasos anteriores, desactívalos o elimínalos.',
                className='alarm-guided__notice',
            ),
            *kept,
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
