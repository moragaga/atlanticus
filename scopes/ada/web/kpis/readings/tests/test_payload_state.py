from __future__ import annotations

import pytest

from ada.web.kpis.readings import KpiPayloadDataState, map_kpi_payload_data_state


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('ok', KpiPayloadDataState.OK),
        ('unshift', KpiPayloadDataState.UNSHIFT),
        ('error', KpiPayloadDataState.ERROR),
    ],
)
def test_payload_state_mapping_accepts_only_declared_states(raw, expected):
    assert map_kpi_payload_data_state(raw) is expected


@pytest.mark.parametrize('raw', [None, '', 'OK', 'Unshift', 'ready', 'stale', 0, True, {}, []])
def test_payload_state_mapping_rejects_undeclared_values(raw):
    with pytest.raises(ValueError, match='KPI payload data_state'):
        map_kpi_payload_data_state(raw)

