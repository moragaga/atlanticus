from __future__ import annotations

import pytest

from ada.web.ui.display_status import DisplayValue
from ada.web.ui.stockpile import StockpileDefinition, StockpileValues, StockpileVariant
from ada.web.ui.stockpile.models import validate_stockpile_values


def test_variable_height_uses_two_independent_readings():
    definition = StockpileDefinition(
        key='pile_a', variant=StockpileVariant.VARIABLE_HEIGHT, scale_max_m=28
    )
    values = StockpileValues(percent=DisplayValue.ok('65'), height_m=DisplayValue.ok('18,2'))
    validate_stockpile_values(definition, values)
    assert values.percent.value == '65'
    assert values.height_m.value == '18,2'


def test_fixed_profile_has_no_height_contract():
    definition = StockpileDefinition(key='anywhere', variant=StockpileVariant.FIXED_PROFILE)
    validate_stockpile_values(definition, StockpileValues(percent=DisplayValue.empty()))
    with pytest.raises(ValueError, match='cannot specify height_m'):
        validate_stockpile_values(
            definition, StockpileValues(DisplayValue.ok('65'), DisplayValue.ok('8'))
        )


@pytest.mark.parametrize('scale', [None, 0, -1, True, float('inf'), float('nan'), '28'])
def test_variable_height_rejects_invalid_scale(scale):
    with pytest.raises(ValueError, match='scale_max_m'):
        StockpileDefinition(key='pile', variant=StockpileVariant.VARIABLE_HEIGHT, scale_max_m=scale)


def test_definition_rejects_invalid_colors_and_size():
    with pytest.raises(ValueError, match='percentage_text_color'):
        StockpileDefinition(
            key='pile', variant=StockpileVariant.FIXED_PROFILE, percentage_text_color='green'
        )
    with pytest.raises(ValueError, match='max_width_px'):
        StockpileDefinition(key='pile', variant=StockpileVariant.FIXED_PROFILE, max_width_px=0)


def test_missing_values_use_display_value_not_null():
    with pytest.raises(TypeError, match='DisplayValue'):
        StockpileValues(percent=None)
    with pytest.raises(ValueError, match='require height_m'):
        validate_stockpile_values(
            StockpileDefinition(
                key='pile', variant=StockpileVariant.VARIABLE_HEIGHT, scale_max_m=28
            ),
            StockpileValues(percent=DisplayValue.empty()),
        )
