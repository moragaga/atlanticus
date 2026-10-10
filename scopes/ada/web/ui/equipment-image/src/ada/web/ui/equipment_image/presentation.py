from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, build_display_status_icon

from .models import EquipmentStateImage
from .module import ADA_EQUIPMENT_IMAGE_ASSET_LAYER

_EQUIPMENT_STATES = {
    'chancador': frozenset({'operando', 'detenido', 'mantencion'}),
    'correa_stmg': frozenset({'operando', 'detenido'}),
    'sag': frozenset({'operando', 'detenido'}),
    'molino_bolas': frozenset({'operando', 'detenido'}),
    'vertimil': frozenset({'operando', 'detenido'}),
    'bomba': frozenset({'operando', 'detenido'}),
    'espesador': frozenset({'operando', 'detenido'}),
    'str': frozenset({'operando', 'detenido'}),
}


def build_equipment_state_image(model: EquipmentStateImage) -> Component:
    if not isinstance(model, EquipmentStateImage):
        raise TypeError('model must be EquipmentStateImage')
    if model.image not in _EQUIPMENT_STATES:
        raise ValueError(f'Unsupported equipment image: {model.image}')

    status = model.state.status
    if status is DisplayStatus.OK:
        raw_state = model.state.value
        if isinstance(raw_state, str):
            operational_state = raw_state.strip().lower()
        else:
            operational_state = ''
        if operational_state in _EQUIPMENT_STATES[model.image]:
            visual = html.Img(
                src=(
                    f'/assets/{ADA_EQUIPMENT_IMAGE_ASSET_LAYER.target_name}'
                    f'/img/equipment/{model.image}/{operational_state}.svg'
                ),
                alt=_alternative(model.label, operational_state),
                title=_alternative(model.label, operational_state),
                className=_classes('ada-equipment-image__image', model.image_class_name),
            )
        else:
            visual = _status_icon(DisplayStatus.INVALID, model.image_class_name)
    else:
        visual = _status_icon(status, model.image_class_name)

    return html.Div(
        className=f'ada-equipment-image ada-equipment-image--{model.label_position.value}',
        children=[
            (
                html.Span(
                    model.label,
                    className=_classes('ada-equipment-image__label', model.label_class_name),
                )
                if model.label is not None
                else None
            ),
            visual,
        ],
    )


def _status_icon(status: DisplayStatus, class_name: str | None) -> Component:
    icon = build_display_status_icon(
        status,
        class_name=_classes('ada-equipment-image__image', class_name),
    )
    if icon is None:
        raise ValueError('Equipment image status icon cannot be resolved')
    return icon


def _alternative(label: str | None, state: str) -> str:
    return f'{label}: {state}' if label else f'Estado de equipo: {state}'


def _classes(base: str, custom: str | None) -> str:
    return ' '.join(part for part in (base, custom) if part)
