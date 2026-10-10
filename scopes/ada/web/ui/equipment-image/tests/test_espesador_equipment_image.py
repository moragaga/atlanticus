from __future__ import annotations

import pytest

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.equipment_image import EquipmentStateImage, build_equipment_state_image


def _image(component):
    return next(child for child in component.children if getattr(child, 'src', None) is not None)


@pytest.mark.parametrize('state', ['operando', 'detenido'])
def test_espesador_image_uses_declared_future_asset_path(state):
    component = build_equipment_state_image(
        EquipmentStateImage(image='espesador', state=DisplayValue.ok(state))
    )
    assert _image(component).src.endswith(f'/img/equipment/espesador/{state}.svg')


def test_espesador_without_state_uses_shared_not_mapped_icon():
    component = build_equipment_state_image(
        EquipmentStateImage(image='espesador', state=DisplayValue.not_mapped())
    )
    assert _image(component).src.endswith('/img/status/not-mapped.svg')
