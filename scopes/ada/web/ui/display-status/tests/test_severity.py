from __future__ import annotations

import pytest

from ada.web.ui.display_status import ValueSeverity, map_value_severity_code


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        (None, ValueSeverity.NEUTRAL),
        ('0', ValueSeverity.NEUTRAL),
        ('1', ValueSeverity.DANGER),
        ('2', ValueSeverity.WARNING),
    ],
)
def test_value_severity_codes_remain_textual(raw, expected):
    assert map_value_severity_code(raw) is expected


@pytest.mark.parametrize('raw', [0, 1, 2, True, False, '', '3', '01', 'warning', {}, []])
def test_value_severity_rejects_noncontractual_codes(raw):
    with pytest.raises(ValueError, match='Value severity code'):
        map_value_severity_code(raw)
