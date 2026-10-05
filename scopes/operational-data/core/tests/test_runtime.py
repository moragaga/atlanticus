from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from atlanticus.operational_data.core import DataInputContext, RuntimeFrameContext


@dataclass
class FakeFrameContext:
    dataframe: object

    def last_row(self) -> object:
        return {'a': 2}

    def last_value(self, column: str, default: Any = None) -> Any:
        return {'a': 2}.get(column, default)

    def last_value_number(self, column: str, default: float | None = None) -> float | None:
        value = {'a': 2.0}.get(column)
        return default if value is None else value


def test_runtime_frame_contract_exposes_helpers() -> None:
    frame = FakeFrameContext(dataframe=[{'a': 1}, {'a': 2}])
    assert isinstance(frame, RuntimeFrameContext)
    assert frame.last_row() == {'a': 2}
    assert frame.last_value('a') == 2
    assert frame.last_value_number('a') == 2.0


def test_data_input_context_rejects_invalid_frames() -> None:
    with pytest.raises(TypeError, match='invalid runtime frame'):
        DataInputContext({'actual': object()})
