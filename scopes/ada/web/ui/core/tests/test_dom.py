import pytest

from ada.web.ui.core import (
    component_identity_attributes,
    slot_identity_attributes,
    subcomponent_identity_attributes,
)


def test_dom_identity_attributes_expose_stable_component_subcomponent_and_slot_keys() -> None:
    assert component_identity_attributes('grinding') == {'data-ada-component-key': 'grinding'}
    assert subcomponent_identity_attributes('flotation_selective') == {
        'data-ada-subcomponent-key': 'flotation_selective'
    }
    assert slot_identity_attributes('center') == {'data-ada-slot-key': 'center'}


@pytest.mark.parametrize('value', ('', 'Center', 'center-slot', ' center'))
def test_dom_identity_rejects_invalid_keys(value: str) -> None:
    with pytest.raises(ValueError, match='Invalid ADA DOM'):
        component_identity_attributes(value)
    with pytest.raises(ValueError, match='Invalid ADA DOM'):
        subcomponent_identity_attributes(value)
