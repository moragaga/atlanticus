from __future__ import annotations

import pytest

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.equipment_image import EquipmentStateImage, build_equipment_state_image


def _image(component):
    items = component.children
    images = [item for item in items if getattr(item, 'src', None)]
    assert len(images) == 1
    return images[0]


@pytest.mark.parametrize('family', ['vertimil', 'bomba'])
@pytest.mark.parametrize('state', ['operando', 'detenido'])
def test_flotacion_family_resolves_expected_asset_path(family, state):
    component = build_equipment_state_image(
        EquipmentStateImage(image=family, state=DisplayValue.ok(state), label='EQ-1')
    )
    image = _image(component)
    assert image.src.endswith(f'/img/equipment/{family}/{state}.svg')
    assert image.alt == f'EQ-1: {state}'


@pytest.mark.parametrize('family', ['vertimil', 'bomba'])
def test_flotacion_family_preserves_missing_state_icon(family):
    component = build_equipment_state_image(
        EquipmentStateImage(image=family, state=DisplayValue.not_mapped())
    )
    assert _image(component).src.endswith('/img/status/not-mapped.svg')
