from __future__ import annotations

from ada.web.kpis.collector.models import KpiCollectorRefreshResult, KpiCollectorRefreshStatus
from ada.web.kpis.collector.runtime import AdaKpiCollectorPollingRuntime
from atlanticus.web.observability import WebObservability
import logging


class Reader:
    def __init__(self, status=KpiCollectorRefreshStatus.MISSING):
        self.status = status
        self.fail = False

    def refresh_latest(self):
        if self.fail:
            raise RuntimeError('Source unavailable')
        return KpiCollectorRefreshResult(self.status)

    def refresh_timeseries(self):
        return KpiCollectorRefreshResult(KpiCollectorRefreshStatus.MISSING)


def test_initial_readiness_distinguishes_pending_empty_error_and_recovery():
    reader = Reader()
    observability = WebObservability(
        application='initial-state-test',
        logger=logging.getLogger('test.kpi.initial-state'),
        json_output=False,
    )
    runtime = AdaKpiCollectorPollingRuntime(reader, observability=observability)
    assert runtime.initial_latest_state == 'pending'
    runtime.poll_due(now=0.0)
    assert runtime.initial_latest_state == 'empty'
    reader.fail = True
    runtime.poll_due(now=10.0)
    assert runtime.initial_latest_state == 'error'
    reader.fail = False
    reader.status = KpiCollectorRefreshStatus.UPDATED
    runtime.poll_due(now=20.0)
    assert runtime.initial_latest_state == 'ready'
