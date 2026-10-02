import tomllib
from pathlib import Path


def test_history_package_has_only_shared_contract_dependencies() -> None:
    root = Path(__file__).resolve().parents[1]
    with (root / 'pyproject.toml').open('rb') as stream:
        project = tomllib.load(stream)['project']

    assert project['dependencies'] == [
        'atlanticus-datasets==1.0.0',
        'pyarrow==25.0.0',
    ]


def test_history_package_does_not_own_runtime_or_transport() -> None:
    root = Path(__file__).resolve().parents[1] / 'src'
    forbidden = (
        'ada.processes',
        'ada.web',
        'atlanticus.connectivity',
        'atlanticus.runtime',
        'atlanticus.state',
        'atlanticus.datasets.runtime',
        'atlanticus.datasets.parquet',
        'pathlib',
        'os.',
    )

    for path in root.rglob('*.py'):
        text = path.read_text(encoding='utf-8')
        assert all(token not in text for token in forbidden), path
