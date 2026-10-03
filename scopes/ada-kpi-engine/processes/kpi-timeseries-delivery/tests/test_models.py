from datetime import UTC, datetime

import pytest

from ada.kpis.core import KpiWatermark
from ada.processes.kpi_timeseries_delivery.models import KpiTimeseriesCheckpoint


def test_checkpoint_requires_registry_digest():
    with pytest.raises(Exception, match='sha256'):
        KpiTimeseriesCheckpoint(
            watermark=KpiWatermark(datetime(2026, 9, 1, tzinfo=UTC)),
            registry_revision='r1',
            registry_digest='invalid',
        )
