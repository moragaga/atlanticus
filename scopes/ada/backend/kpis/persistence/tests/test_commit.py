from pathlib import Path

import pytest

from ada.kpis.persistence import KpiEvaluationWriteStatus, KpiPersistence, KpiPersistenceOrderError
from tests.support import batch, watermark


def persistence(tmp_path: Path) -> KpiPersistence:
    return KpiPersistence.from_runtime(volume_path=tmp_path, application='ada-test')


def test_commit_writes_batch_before_advancing_watermark(tmp_path: Path) -> None:
    repository = persistence(tmp_path)
    result = repository.commit(batch(10))
    assert result.before is None
    assert result.after == watermark(10)
    assert result.write_status is KpiEvaluationWriteStatus.CREATED
    assert repository.committed_watermark() == watermark(10)
    assert repository.read_committed_after() == (batch(10),)


def test_retry_is_idempotent(tmp_path: Path) -> None:
    repository = persistence(tmp_path)
    repository.commit(batch(10))
    retry = repository.commit(batch(10))
    assert retry.write_status is KpiEvaluationWriteStatus.UNCHANGED
    assert repository.read_committed_after() == (batch(10),)


def test_conflicting_retry_is_rejected(tmp_path: Path) -> None:
    repository = persistence(tmp_path)
    repository.commit(batch(10, value=1.0))
    with pytest.raises(Exception, match='conflicts'):
        repository.commit(batch(10, value=2.0))


def test_watermark_never_moves_backwards(tmp_path: Path) -> None:
    repository = persistence(tmp_path)
    repository.commit(batch(20))
    with pytest.raises(KpiPersistenceOrderError, match='backwards'):
        repository.commit(batch(10))


def test_reader_never_exposes_uncommitted_future_batch(tmp_path: Path) -> None:
    repository = persistence(tmp_path)
    repository.commit(batch(10))
    future_path = (
        tmp_path
        / 'ada-test/datasets/kpis/evaluations/year=2026/month=08/day=31/hour=12/20260831T122000Z.json'
    )
    future_path.parent.mkdir(parents=True, exist_ok=True)
    future_path.write_text('{invalid future document', encoding='utf-8')
    assert repository.read_committed_after() == (batch(10),)
