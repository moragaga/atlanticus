from datetime import UTC, datetime

import pytest

from ada.kpis.core import KpiWatermark
from ada.processes.kpi_timeseries_delivery.models import KpiTimeseriesCheckpoint


def test_checkpoint_rejects_blank_revision():
    with pytest.raises(ValueError):
        KpiTimeseriesCheckpoint(
            watermark=KpiWatermark(datetime(2026, 9, 1, tzinfo=UTC)),
            configuration_revision='',
        )
