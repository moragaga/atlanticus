from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'src/ada/processes/kpi_historian'


def test_process_does_not_depend_on_web_or_other_processes() -> None:
    forbidden = (
        'ada.web',
        'ada.processes.kpi_runtime',
        'ada.processes.kpi_delivery',
        'ada.processes.kpis_historian',
        'atlanticus.data_producers',
        'CosmosClient',
    )
    content = '\n'.join(path.read_text(encoding='utf-8') for path in SOURCE.glob('*.py'))

    for token in forbidden:
        assert token not in content


def test_history_contract_is_consumed_instead_of_redeclared() -> None:
    content = (SOURCE / 'history.py').read_text(encoding='utf-8')

    assert 'DatasetDefinition(' not in content
    assert 'pa.schema(' not in content
    assert "DatasetKey(namespace=('kpis',), name='history')" not in content


def test_historian_materializers_do_not_own_pyarrow_or_raw_parquet_io() -> None:
    content = '\n'.join(
        (SOURCE / name).read_text(encoding='utf-8') for name in ('history.py', 'rolling.py')
    )

    assert 'import pyarrow' not in content
    assert 'from pyarrow' not in content
    assert 'atlanticus.datasets.parquet' not in content
    assert 'pq.read_table' not in content
    assert 'pq.write_table' not in content
    assert 'os.replace' not in content
    assert 'tempfile' not in content
