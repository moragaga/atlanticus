import math

import pytest

from ada.kpis.history import KpiHistoryContractError, decode_history_value, encode_history_value


def test_history_value_encoding_is_canonical() -> None:
    first = {'b': [2, True], 'a': {'z': 'á', 'x': 1.5}}
    second = {'a': {'x': 1.5, 'z': 'á'}, 'b': [2, True]}

    assert encode_history_value(first) == encode_history_value(second)
    assert encode_history_value(first) == '{"a":{"x":1.5,"z":"á"},"b":[2,true]}'


def test_history_value_round_trip_preserves_json_types() -> None:
    value = {'number': 12.5, 'text': 'ok', 'flag': False, 'items': [1, None, 'x']}

    encoded = encode_history_value(value)

    assert decode_history_value(encoded) == value
    assert encode_history_value(None) is None
    assert decode_history_value(None) is None


def test_history_value_rejects_non_json_and_non_finite_numbers() -> None:
    with pytest.raises(KpiHistoryContractError, match='valid JSON'):
        encode_history_value({1, 2})
    with pytest.raises(KpiHistoryContractError, match='valid JSON'):
        encode_history_value(math.inf)
    with pytest.raises(KpiHistoryContractError, match='invalid JSON'):
        decode_history_value('NaN')
    with pytest.raises(KpiHistoryContractError, match='non-finite'):
        decode_history_value('1e999')


def test_decode_requires_encoded_text_or_none() -> None:
    with pytest.raises(TypeError, match='str or None'):
        decode_history_value(42)  # type: ignore[arg-type]
