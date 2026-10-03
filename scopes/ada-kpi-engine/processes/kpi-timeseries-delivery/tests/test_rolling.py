from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ada.kpis.history import KpiHistorianAuthority, KpiRollingMetadata
from ada.kpis.history.dataset import (
    rolling_definition,
    rolling_table,
    rolling_target,
)
from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryRepositoryError,
)
from ada.processes.kpi_timeseries_delivery.rolling import (
    KpiTimeseriesRollingRepository,
)
from atlanticus.datasets.parquet import ParquetDatasetStore
from atlanticus.datasets.runtime import DatasetRuntime


def _authority() -> KpiHistorianAuthority:
    return KpiHistorianAuthority(
        watermark_utc=datetime(
            2026,
            10,
            2,
            20,
            0,
            tzinfo=UTC,
        ),
    )


def _runtime(tmp_path: Path) -> DatasetRuntime:
    return DatasetRuntime(store=ParquetDatasetStore(root=tmp_path))


def _write_rolling(
    runtime: DatasetRuntime,
    *,
    authority: KpiHistorianAuthority,
    points: dict[datetime, dict[str, str]],
    value_types: dict[str, str],
) -> None:
    timestamps = sorted(points)
    metadata = KpiRollingMetadata(
        watermark_utc=authority.watermark_utc,
        historian_revision=authority.revision,
        coverage_start_utc=None if not timestamps else timestamps[0],
        coverage_end_utc=None if not timestamps else timestamps[-1],
        value_types=value_types,
    )
    runtime.replace(
        definition=rolling_definition(),
        target=rolling_target(),
        data=rolling_table(
            metadata=metadata,
            points=points,
        ),
    )


def test_rolling_reads_only_requested_existing_series(
    tmp_path: Path,
) -> None:
    authority = _authority()
    runtime = _runtime(tmp_path)
    first = datetime(
        2026,
        10,
        2,
        19,
        58,
        tzinfo=UTC,
    )
    second = datetime(
        2026,
        10,
        2,
        20,
        0,
        tzinfo=UTC,
    )
    _write_rolling(
        runtime,
        authority=authority,
        points={
            first: {'a': '1', 'b': '2'},
            second: {'a': '3', 'b': '4'},
        },
        value_types={
            'a': 'integer',
            'b': 'integer',
        },
    )

    result = KpiTimeseriesRollingRepository(runtime=runtime).read(
        authority=authority,
        keys=('b',),
        start_utc=datetime(
            2026,
            10,
            2,
            19,
            57,
            tzinfo=UTC,
        ),
        end_utc=authority.watermark_utc,
    )

    assert tuple(result.histories) == ('b',)
    assert dict(result.histories['b'].values) == {
        first: '2',
        second: '4',
    }
    assert result.histories['b'].value_type == 'integer'


def test_missing_required_physical_column_becomes_virtual_null_series(
    tmp_path: Path,
) -> None:
    authority = _authority()
    runtime = _runtime(tmp_path)
    _write_rolling(
        runtime,
        authority=authority,
        points={authority.watermark_utc: {'present': '1'}},
        value_types={'present': 'integer'},
    )

    result = KpiTimeseriesRollingRepository(runtime=runtime).read(
        authority=authority,
        keys=('missing',),
        start_utc=datetime(
            2026,
            10,
            2,
            19,
            0,
            tzinfo=UTC,
        ),
        end_utc=authority.watermark_utc,
    )

    assert dict(result.histories) == {}


def test_existing_series_keeps_type_when_window_has_no_physical_points(
    tmp_path: Path,
) -> None:
    authority = _authority()
    runtime = _runtime(tmp_path)
    _write_rolling(
        runtime,
        authority=authority,
        points={
            datetime(
                2026,
                10,
                2,
                19,
                0,
                tzinfo=UTC,
            ): {'state': 'RUN'}
        },
        value_types={'state': 'text'},
    )

    result = KpiTimeseriesRollingRepository(runtime=runtime).read(
        authority=authority,
        keys=('state',),
        start_utc=datetime(
            2026,
            10,
            2,
            19,
            30,
            tzinfo=UTC,
        ),
        end_utc=authority.watermark_utc,
    )

    assert result.histories['state'].value_type == 'text'
    assert dict(result.histories['state'].values) == {}


def test_empty_rolling_publication_is_readable(
    tmp_path: Path,
) -> None:
    authority = _authority()
    runtime = _runtime(tmp_path)
    _write_rolling(
        runtime,
        authority=authority,
        points={},
        value_types={},
    )

    result = KpiTimeseriesRollingRepository(runtime=runtime).read(
        authority=authority,
        keys=('missing',),
        start_utc=datetime(
            2026,
            10,
            2,
            19,
            0,
            tzinfo=UTC,
        ),
        end_utc=authority.watermark_utc,
    )

    assert dict(result.histories) == {}


def test_rolling_rejects_revision_mismatch_with_authority(
    tmp_path: Path,
) -> None:
    source_authority = _authority()
    runtime = _runtime(tmp_path)
    _write_rolling(
        runtime,
        authority=source_authority,
        points={source_authority.watermark_utc: {'a': '1'}},
        value_types={'a': 'integer'},
    )
    newer = KpiHistorianAuthority(
        watermark_utc=datetime(
            2026,
            10,
            2,
            20,
            0,
            30,
            tzinfo=UTC,
        ),
    )

    with pytest.raises(
        KpiTimeseriesDeliveryRepositoryError,
        match='not coherent',
    ):
        KpiTimeseriesRollingRepository(runtime=runtime).read(
            authority=newer,
            keys=('a',),
            start_utc=datetime(
                2026,
                10,
                2,
                19,
                0,
                tzinfo=UTC,
            ),
            end_utc=datetime(
                2026,
                10,
                2,
                20,
                0,
                tzinfo=UTC,
            ),
        )


def test_rolling_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(
        KpiTimeseriesDeliveryRepositoryError,
        match='was not found',
    ):
        KpiTimeseriesRollingRepository(runtime=_runtime(tmp_path)).read(
            authority=_authority(),
            keys=('a',),
            start_utc=datetime(
                2026,
                10,
                2,
                19,
                0,
                tzinfo=UTC,
            ),
            end_utc=datetime(
                2026,
                10,
                2,
                20,
                0,
                tzinfo=UTC,
            ),
        )
