from __future__ import annotations

import pytest

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.equipment_image import (
    EquipmentStateImage,
    LabelPosition,
    build_equipment_state_image,
)


def _properties(component):
    if hasattr(component, 'to_plotly_json'):
        props = component.to_plotly_json()['props']
        yield props
        yield from _properties(props.get('children'))
    elif isinstance(component, (list, tuple)):
        for child in component:
            yield from _properties(child)


def _image(component):
    images = [props for props in _properties(component) if 'src' in props]
    assert len(images) == 1
    return images[0]


def _text(component):
    if hasattr(component, 'to_plotly_json'):
        yield from _text(component.to_plotly_json()['props'].get('children'))
    elif isinstance(component, (tuple, list)):
        for child in component:
            yield from _text(child)
    elif isinstance(component, str):
        yield component


@pytest.mark.parametrize(
    ('image', 'state'),
    [
        ('chancador', 'operando'),
        ('chancador', 'detenido'),
        ('chancador', 'mantencion'),
        ('correa_stmg', 'operando'),
        ('correa_stmg', 'detenido'),
    ],
)
def test_known_equipment_state_resolves_declared_svg(image, state):
    component = build_equipment_state_image(
        EquipmentStateImage(image=image, state=DisplayValue.ok(state))
    )
    assert _image(component)['src'].endswith(f'/img/equipment/{image}/{state}.svg')
    assert _image(component)['alt'] == f'Estado de equipo: {state}'
    assert tuple(_text(component)) == ()


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (DisplayValue.not_mapped(), 'not-mapped.svg'),
        (DisplayValue.empty(), 'empty-data.svg'),
        (DisplayValue.invalid(), 'invalid-data.svg'),
        (DisplayValue.error(), 'internal-error.svg'),
        (DisplayValue.ok('desconocido'), 'invalid-data.svg'),
        (DisplayValue.ok(987), 'invalid-data.svg'),
        (DisplayValue.ok('mantencion'), 'invalid-data.svg'),
    ],
)
def test_degraded_or_unrecognized_state_uses_existing_system_icon(value, expected):
    component = build_equipment_state_image(EquipmentStateImage(image='correa_stmg', state=value))
    assert _image(component)['src'].endswith(f'/img/status/{expected}')


def test_label_is_supplied_by_consumer_and_used_as_accessible_name():
    component = build_equipment_state_image(
        EquipmentStateImage(
            image='chancador',
            state=DisplayValue.ok('operando'),
            label='CH-42',
            label_position=LabelPosition.RIGHT,
        )
    )
    assert 'CH-42' in tuple(_text(component))
    assert _image(component)['alt'] == 'CH-42: operando'


@pytest.mark.parametrize('value', [None, 'operando', {'status': 'ok', 'value': 'operando'}])
def test_state_must_use_shared_display_value_contract(value):
    with pytest.raises(TypeError, match='DisplayValue'):
        EquipmentStateImage(image='chancador', state=value)


def test_label_position_rejects_unknown_value():
    with pytest.raises(TypeError, match='LabelPosition'):
        EquipmentStateImage(
            image='chancador',
            state=DisplayValue.ok('operando'),
            label_position='center',
        )


def test_unknown_equipment_family_is_rejected():
    with pytest.raises(ValueError, match='Unsupported equipment'):
        build_equipment_state_image(
            EquipmentStateImage(image='../some-file', state=DisplayValue.ok('operando'))
        )


def test_untrusted_operational_state_cannot_resolve_asset_path():
    component = build_equipment_state_image(
        EquipmentStateImage(image='chancador', state=DisplayValue.ok('../../operando.svg'))
    )
    assert _image(component)['src'].endswith('/img/status/invalid-data.svg')
