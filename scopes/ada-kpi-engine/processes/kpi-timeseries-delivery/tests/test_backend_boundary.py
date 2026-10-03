from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/ada/processes/kpi_timeseries_delivery'


def test_timeseries_process_does_not_use_pyarrow_or_raw_parquet_io() -> None:
    content = '\n'.join(path.read_text(encoding='utf-8') for path in SOURCE.glob('*.py'))

    assert 'import pyarrow' not in content
    assert 'from pyarrow' not in content
    assert 'pq.read_table' not in content
    assert 'pq.write_table' not in content
