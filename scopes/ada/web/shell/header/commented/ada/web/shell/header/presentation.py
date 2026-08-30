# El Header sólo ancla componentes ya construidos. Cada capability conserva su propia presentación.
from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.ui.core import component_identity_attributes, slot_identity_attributes


def build_ada_operational_header(
    *,
    brand: Component,
    global_indicators: Component | None = None,
    alarm_management: Component | None = None,
    alarm_status: Component | None = None,
    time_status: Component | None = None,
    desktop_navigation_trigger: Component | None = None,
    mobile_navigation_trigger: Component | None = None,
) -> html.Header:
    # La fila primaria mantiene el orden horizontal ya aprobado para los bloques operacionales.
    row_children: list[Component] = [
        _build_slot('brand', brand, 'ada-operational-header__brand-slot'),
        _build_slot(
            'global_indicators',
            global_indicators,
            'ada-operational-header__global-indicators-slot',
        ),
        _build_slot(
            'alarm_management',
            alarm_management,
            'ada-operational-header__alarm-management-slot',
        ),
        _build_slot(
            'alarm_status',
            alarm_status,
            'ada-operational-header__alarm-status-slot',
        ),
    ]
    if mobile_navigation_trigger is not None:
        row_children.append(
            html.Div(
                mobile_navigation_trigger,
                className=(
                    'ada-operational-header__mobile-navigation ada-navigation__mobile-anchor'
                ),
                **slot_identity_attributes('navigation_mobile'),
            )
        )

    # El trigger desktop se ancla únicamente a la fila primaria para que el nuevo strip inferior
    # de Time Status no cambie su centro vertical ni invada los bloques operacionales.
    primary_children: list[Component] = [
        html.Div(
            row_children,
            className='ada-operational-header',
        )
    ]
    if desktop_navigation_trigger is not None:
        primary_children.append(
            html.Div(
                desktop_navigation_trigger,
                className='ada-operational-header__desktop-navigation',
                **slot_identity_attributes('navigation_desktop'),
            )
        )

    # Time Status vive bajo la fila existente pero sigue dentro del Header. El slot siempre existe
    # como contrato DOM y se colapsa completamente cuando la composition root no inyecta contenido.
    return html.Header(
        [
            html.Div(
                primary_children,
                className='ada-operational-header__primary ada-navigation__anchor-host',
            ),
            _build_slot(
                'time_status',
                time_status,
                'ada-operational-header__time-status-slot',
            ),
        ],
        className='ada-operational-header-shell',
        **component_identity_attributes('operational_header'),
    )


def _build_slot(slot_key: str, content: Component | None, class_name: str) -> html.Div:
    # Los slots vacíos siguen existiendo en el contrato DOM, pero CSS los colapsa sin placeholders.
    attributes = slot_identity_attributes(slot_key)
    attributes['data-slot-empty'] = 'true' if content is None else 'false'
    return html.Div(
        [] if content is None else [content],
        className=class_name,
        **attributes,
    )
