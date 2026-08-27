from __future__ import annotations

from dataclasses import dataclass

import pytest

from ada.web.ui.display_status import DisplayStatus, DisplayValue, coerce_display_value


def test_display_value_enforces_payload_contract() -> None:
    assert DisplayValue.ok(42).value == 42
    assert DisplayValue.empty().value is None

    with pytest.raises(ValueError, match='OK display value requires a concrete value'):
        DisplayValue(DisplayStatus.OK)
    with pytest.raises(ValueError, match='Degraded display value cannot expose a value'):
        DisplayValue(DisplayStatus.ERROR, 42)


def test_coerce_distinguishes_mapping_empty_and_normal_values() -> None:
    assert coerce_display_value(10) == DisplayValue.ok(10)
    assert coerce_display_value(None) == DisplayValue.empty()
    assert coerce_display_value('ignored', present=False) == DisplayValue.not_mapped()


def test_coerce_reads_status_payload_contracts() -> None:
    assert coerce_display_value({'status': 'ok', 'value': 12}) == DisplayValue.ok(12)
    assert coerce_display_value({'status': 'ok', 'value': None}) == DisplayValue.invalid()
    assert coerce_display_value({'status': 'invalid'}) == DisplayValue.invalid()
    assert coerce_display_value({'status': 'unknown'}) == DisplayValue.error()


@dataclass
class _ValueObject:
    status: str
    value: object | None = None


def test_coerce_reads_object_contracts() -> None:
    assert coerce_display_value(_ValueObject('empty')) == DisplayValue.empty()
    assert coerce_display_value(_ValueObject('ok', 7)) == DisplayValue.ok(7)
