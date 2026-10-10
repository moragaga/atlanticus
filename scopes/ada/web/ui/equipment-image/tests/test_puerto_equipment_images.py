from __future__ import annotations

from importlib.resources import files

import pytest

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.equipment_image import EquipmentStateImage, build_equipment_state_image


@pytest.mark.parametrize('family', ['barco', 'filtro'])
@pytest.mark.parametrize('state', ['operando', 'detenido'])
def test_puerto_equipment_resolves_packaged_svg(family, state):
    component = build_equipment_state_image(
        EquipmentStateImage(image=family, state=DisplayValue.ok(state))
    )
    images = [item for item in component.children if getattr(item, 'src', None)]
    assert len(images) == 1
    assert images[0].src.endswith(f'/img/equipment/{family}/{state}.svg')
    asset = files('ada.web.ui.equipment_image').joinpath(
        'resources', 'img', 'equipment', family, f'{state}.svg'
    )
    assert asset.is_file()


@pytest.mark.parametrize('family', ['barco', 'filtro'])
def test_puerto_equipment_preserves_degraded_status(family):
    component = build_equipment_state_image(
        EquipmentStateImage(image=family, state=DisplayValue.error())
    )
    images = [item for item in component.children if getattr(item, 'src', None)]
    assert len(images) == 1
    assert images[0].src.endswith('/img/status/internal-error.svg')
