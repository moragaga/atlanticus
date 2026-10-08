from __future__ import annotations

import pytest

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.stockpile import StockpileItem, StockpilePanel


def _item(key: str = 'pile_1') -> StockpileItem:
    return StockpileItem(
        key=key,
        label='Pila Mina',
        percentage=DisplayValue.ok('65'),
        height_m=DisplayValue.ok('18,2'),
    )


def test_panel_accepts_two_independent_display_values_per_pile():
    model = StockpilePanel(items=(_item(), _item('pile_2')), scale_max_m=28)
    assert [item.key for item in model.items] == ['pile_1', 'pile_2']
    assert model.items[0].percentage.value == '65'
    assert model.items[0].height_m.value == '18,2'


@pytest.mark.parametrize('items', [(), (_item(), _item())])
def test_panel_rejects_missing_or_duplicate_piles(items):
    with pytest.raises(ValueError):
        StockpilePanel(items=items, scale_max_m=28)


@pytest.mark.parametrize('scale', [0, -1, True, float('inf'), float('nan'), '28'])
def test_panel_rejects_invalid_visual_scale(scale):
    with pytest.raises(ValueError, match='scale'):
        StockpilePanel(items=(_item(),), scale_max_m=scale)


@pytest.mark.parametrize('value', [None, '65', {'status': 'ok', 'value': '65'}])
def test_item_requires_display_value_contract(value):
    with pytest.raises(TypeError, match='DisplayValue'):
        StockpileItem(
            key='pile_1', label='Pila 1', percentage=value, height_m=DisplayValue.ok('18')
        )


def test_labels_are_supplied_by_consumer():
    model = _item()
    assert model.label == 'Pila Mina'
    assert model.key == 'pile_1'


def test_empty_label_and_invalid_optional_classes_are_rejected():
    with pytest.raises(ValueError, match='label'):
        StockpileItem(
            key='pile_1', label=' ', percentage=DisplayValue.ok('2'), height_m=DisplayValue.ok('3')
        )
    with pytest.raises(ValueError, match='class_name'):
        StockpilePanel(items=(_item(),), scale_max_m=28, class_name=' ')
