from __future__ import annotations

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.equipment_image import EquipmentStateImage, build_equipment_state_image


def _visual(component):
    return next(item for item in component.children if hasattr(item, 'src'))


def test_str_images_use_explicit_states_only():
    for state in ('operando', 'detenido'):
        component = build_equipment_state_image(
            EquipmentStateImage(image='str', state=DisplayValue.ok(state))
        )
        assert _visual(component).src.endswith(f'/img/equipment/str/{state}.svg')


def test_unknown_str_state_falls_back_to_invalid_icon():
    component = build_equipment_state_image(
        EquipmentStateImage(image='str', state=DisplayValue.ok('unknown'))
    )
    assert _visual(component).src.endswith('/img/status/invalid-data.svg')
