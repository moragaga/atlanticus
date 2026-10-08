from __future__ import annotations

import pytest

from ada.web.ui.display_status import DisplayStatus, DisplayValue
from ada.web.ui.stockpile.values import resolve_stockpile_reading


@pytest.mark.parametrize(
    ('original', 'expected'),
    [('18,2', 18.2), (' 18.20 ', 18.2), ('0', 0.0), ('100', 100.0), ('+2,5', 2.5)],
)
def test_valid_textual_numbers_preserve_original_presentation(original, expected):
    reading = resolve_stockpile_reading(DisplayValue.ok(original), percentage=True)
    assert reading.status is DisplayStatus.OK
    assert reading.number == expected
    assert reading.text == original.strip()


@pytest.mark.parametrize(
    'value', ['NaN', 'Inf', '', '  ', '1,2.3', '65 %', '-1', '101', 'not a number', True]
)
def test_invalid_percentages_use_invalid_status(value):
    reading = resolve_stockpile_reading(DisplayValue.ok(value), percentage=True)
    assert reading.status is DisplayStatus.INVALID
    assert reading.number is None
    assert reading.text is None


@pytest.mark.parametrize('value', ['-0.1', '-5', 'nan', '18 m', '1,000.5'])
def test_invalid_heights_use_invalid_status(value):
    reading = resolve_stockpile_reading(DisplayValue.ok(value), percentage=False)
    assert reading.status is DisplayStatus.INVALID


def test_large_positive_height_is_not_treated_as_invalid_percentage():
    height = resolve_stockpile_reading(DisplayValue.ok('125'), percentage=False)
    assert height.status is DisplayStatus.OK
    assert height.number == 125


@pytest.mark.parametrize(
    ('display', 'status'),
    [
        (DisplayValue.not_mapped(), DisplayStatus.NOT_MAPPED),
        (DisplayValue.empty(), DisplayStatus.EMPTY),
        (DisplayValue.invalid(), DisplayStatus.INVALID),
        (DisplayValue.error(), DisplayStatus.ERROR),
    ],
)
def test_degraded_kpi_status_is_preserved(display, status):
    result = resolve_stockpile_reading(display, percentage=False)
    assert result.status is status
    assert result.number is None
    assert result.text is None
