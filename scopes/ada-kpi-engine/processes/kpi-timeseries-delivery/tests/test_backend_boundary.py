from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/ada/processes/kpi_timeseries_delivery'


def test_timeseries_process_does_not_use_pyarrow_or_raw_parquet_io() -> None:
    content = '\n'.join(path.read_text(encoding='utf-8') for path in SOURCE.glob('*.py'))

    assert 'import pyarrow' not in content
    assert 'from pyarrow' not in content
    assert 'pq.read_table' not in content
    assert 'pq.write_table' not in content


def test_rolling_repository_uses_dataset_runtime_boundary() -> None:
    content = (SOURCE / 'rolling.py').read_text(encoding='utf-8')

    assert 'atlanticus.datasets.parquet' not in content
    assert 'ParquetDatasetStore' not in content
    assert 'ParquetReadError' not in content
    assert 'ParquetValidationError' not in content
    assert 'atlanticus.datasets.runtime' in content
    assert 'scan_table' in content
