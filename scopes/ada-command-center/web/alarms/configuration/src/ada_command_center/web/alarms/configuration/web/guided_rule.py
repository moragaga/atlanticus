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
    del targets, references
    selected = section if section in {item[0] for item in RULE_SECTIONS} else 'general'
    index = next(i for i, item in enumerate(RULE_SECTIONS) if item[0] == selected)
    _, label, help_text = RULE_SECTIONS[index]
    deactivation = children[4]
    if deactivation_enabled is False:
        deactivation = html.Fieldset(deactivation.children[:2], className='alarm-guided__group')
    escalation = children[5]
    if criticality == 'C3':
        escalation = _criticality_three_panel(escalation)
    panels = {
        'general': [children[0], children[1]],
        'evaluation': [children[2]],
        'behavior': [children[3], deactivation, escalation],
        'visual': [children[6]],
    }
    return html.Div(
        [
            html.Nav(
                [
                    html.Button(
                        [
                            html.Span(f'{position + 1:02d}', className='alarm-guided__step-number'),
                            html.Span(item_label),
                        ],
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
                'C3 solo utiliza la herramienta de origen; no admite destinos de escalamiento.',
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
