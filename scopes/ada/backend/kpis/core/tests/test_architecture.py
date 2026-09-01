from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_kpi_core_does_not_recreate_operational_data_ownership() -> None:
    assert not (ROOT / 'src/ada/kpis/core/requirements.py').exists()
    assert not (ROOT / 'src/ada/kpis/core/runtime.py').exists()
    text = '\n'.join(path.read_text(encoding='utf-8') for path in (ROOT / 'src').rglob('*.py'))
    for token in ('KpiPartition', 'KpiSource', 'SourceRequirement', 'ada.data.'):
        assert token not in text.replace('KpiSourceTrace', '')
