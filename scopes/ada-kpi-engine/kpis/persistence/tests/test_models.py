import pytest

from ada.kpis.persistence import KpiEvaluationBatch
from tests.support import batch


def test_batch_round_trip() -> None:
    value = batch(10)
    assert KpiEvaluationBatch.from_payload(value.to_payload()) == value


def test_batch_requires_unique_kpi_keys() -> None:
    value = batch(10)
    with pytest.raises(ValueError, match='unique'):
        KpiEvaluationBatch(value.watermark, value.evaluations * 2)
