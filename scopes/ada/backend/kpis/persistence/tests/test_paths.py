from pathlib import Path

from ada.kpis.persistence import KpiPersistencePaths
from tests.support import watermark


def test_evaluation_path_is_deterministic_and_partitioned(tmp_path: Path) -> None:
    paths = KpiPersistencePaths(tmp_path.resolve())
    assert paths.evaluation_path(watermark(10)).relative_to(tmp_path) == Path(
        'datasets/kpis/evaluations/year=2026/month=08/day=31/hour=12/20260831T121000Z.json'
    )
