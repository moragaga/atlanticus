from __future__ import annotations

import pytest
from dash import html

from ada.web.ui.display_status import DisplayStatus, DisplayValue, resolve_status_visual
from ada.web.ui.equipment_image import EquipmentStateImage, build_equipment_state_image


@pytest.mark.parametrize('equipment', ['sag', 'molino_bolas'])
@pytest.mark.parametrize('operational_state', ['Operando', 'Detenido'])
def test_molienda_equipment_uses_existing_image_asset_contract(equipment, operational_state):
    model = EquipmentStateImage(
        image=equipment,
        state=DisplayValue.ok(operational_state),
        label='Machine',
    )
    result = build_equipment_state_image(model)
    assert isinstance(result.children[1], html.Img)
    assert result.children[1].src.endswith(f'/{equipment}/{operational_state.lower()}.svg')
    assert result.children[1].alt == f'Machine: {operational_state.lower()}'


@pytest.mark.parametrize(
    'status', [DisplayStatus.NOT_MAPPED, DisplayStatus.EMPTY, DisplayStatus.ERROR]
)
def test_degraded_molienda_equipment_preserves_system_indicator(status):
    result = build_equipment_state_image(EquipmentStateImage('sag', DisplayValue(status)))
    assert isinstance(result.children[1], html.Img)
    assert result.children[1].alt == resolve_status_visual(status).alt


def test_unknown_sag_state_is_invalid_instead_of_assuming_detenido():
    result = build_equipment_state_image(EquipmentStateImage('sag', DisplayValue.ok('Unknown')))
    assert result.children[1].alt == resolve_status_visual(DisplayStatus.INVALID).alt
