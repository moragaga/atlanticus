from __future__ import annotations

import pytest

from ada.kpis.core import KpiCatalog
from ada.processes.kpi_runtime.errors import KpiRuntimeWatermarkError
from ada.processes.kpi_runtime.job import KpiRuntimeJob
from ada.processes.kpi_runtime.models import KpiRuntimeOutcome
from ada.processes.kpi_runtime.source_state import PiOperationalWatermarkReader
from atlanticus.operational_data.sources import PiSourceProvider
from atlanticus.state import AtomicStateStore, StateKey
from tests.support import RuntimeContextStub, StaticWatermarkReader, runtime_parts, watermark


def _job(tmp_path, source, *, catalog=None):
    resolved, plan, loader, persistence, reader = runtime_parts(tmp_path, catalog=catalog)
    return (
        KpiRuntimeJob(
            catalog=resolved,
            plan=plan,
            loader=loader,
            persistence=persistence,
            source_watermarks=source,
        ),
        persistence,
        reader,
    )


def test_source_watermark_missing_is_empty(tmp_path) -> None:
    job, persistence, reader = _job(tmp_path, StaticWatermarkReader(None))
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.outcome is KpiRuntimeOutcome.EMPTY
    assert result.reason == 'source_watermark_missing'
    assert persistence.committed_watermark() is None
    assert reader.calls == 0
    assert context.work is False


def test_empty_catalog_does_not_advance_watermark(tmp_path) -> None:
    source = StaticWatermarkReader(watermark(10))
    job, persistence, reader = _job(tmp_path, source, catalog=KpiCatalog(()))
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.reason == 'no_kpis_configured'
    assert persistence.committed_watermark() is None
    assert reader.calls == 0


def test_new_source_watermark_evaluates_and_commits(tmp_path) -> None:
    source = StaticWatermarkReader(watermark(10))
    job, persistence, reader = _job(tmp_path, source)
    context = RuntimeContextStub()

    result = job.run_iteration(context)

    assert result.outcome is KpiRuntimeOutcome.COMPLETED
    assert result.reason == 'evaluated'
    assert result.committed_before is None
    assert result.committed_after == watermark(10)
    assert result.evaluation_count == 1
    assert persistence.committed_watermark() == watermark(10)
    assert reader.calls == 1
    assert context.work is True
    assert context.lease_checks == 1
    assert context.fences == 1
    assert context.execution_counters == {'evaluations_committed': 1}


def test_notpii_recorded_advance_does_not_move_kpi_runtime(tmp_path) -> None:
    store = AtomicStateStore(volume_path=tmp_path, application='notpii-clock')
    key = StateKey(namespace=('producers',), name='notpii')
    store.replace(
        key,
        {
            'producer': 'notpii',
            'revision': 2,
            'source_watermark_utc': '2026-08-31T20:12:00.000000Z',
            'last_change_at_utc': '2026-08-31T20:12:01.000000Z',
            'streams': {
                'interpolated': {
                    'revision': 1,
                    'source_watermark_utc': '2026-08-31T20:10:00.000000Z',
                    'last_change_at_utc': '2026-08-31T20:10:01.000000Z',
                },
                'recorded': {
                    'revision': 2,
                    'source_watermark_utc': '2026-08-31T20:12:00.000000Z',
                    'last_change_at_utc': '2026-08-31T20:12:01.000000Z',
                },
            },
        },
    )
    source = PiOperationalWatermarkReader(store=store, provider=PiSourceProvider.NOTPII)
    job, persistence, reader = _job(tmp_path, source)

    first = job.run_iteration(RuntimeContextStub())

    assert first.reason == 'evaluated'
    assert persistence.committed_watermark() == watermark(10)
    assert reader.calls == 1

    store.replace(
        key,
        {
            'producer': 'notpii',
            'revision': 3,
            'source_watermark_utc': '2026-08-31T20:13:00.000000Z',
            'last_change_at_utc': '2026-08-31T20:13:01.000000Z',
            'streams': {
                'interpolated': {
                    'revision': 1,
                    'source_watermark_utc': '2026-08-31T20:10:00.000000Z',
                    'last_change_at_utc': '2026-08-31T20:10:01.000000Z',
                },
                'recorded': {
                    'revision': 3,
                    'source_watermark_utc': '2026-08-31T20:13:00.000000Z',
                    'last_change_at_utc': '2026-08-31T20:13:01.000000Z',
                },
            },
        },
    )

    second = job.run_iteration(RuntimeContextStub())

    assert second.reason == 'up_to_date'
    assert persistence.committed_watermark() == watermark(10)
    assert reader.calls == 1


def test_same_source_watermark_skips_without_loading(tmp_path) -> None:
    source = StaticWatermarkReader(watermark(10))
    job, persistence, reader = _job(tmp_path, source)
    job.run_iteration(RuntimeContextStub())
    reader.calls = 0

    result = job.run_iteration(RuntimeContextStub())

    assert result.reason == 'up_to_date'
    assert persistence.committed_watermark() == watermark(10)
    assert reader.calls == 0


def test_source_watermark_behind_committed_fails_closed(tmp_path) -> None:
    source = StaticWatermarkReader(watermark(10))
    job, persistence, _reader = _job(tmp_path, source)
    job.run_iteration(RuntimeContextStub())
    source.value = watermark(8)

    with pytest.raises(KpiRuntimeWatermarkError, match='must not be older'):
        job.run_iteration(RuntimeContextStub())

    assert persistence.committed_watermark() == watermark(10)


def test_resolver_error_is_committed_as_kpi_error(tmp_path) -> None:
    resolved, plan, loader, persistence, _reader = runtime_parts(tmp_path)
    spec = next(iter(resolved))

    def explode(_context):
        raise RuntimeError('boom')

    from ada.kpis.core import KpiCatalog, KpiMode, KpiSpec

    failing = KpiCatalog(
        (
            KpiSpec(
                key='test-kpi',
                area=spec.area,
                mode=KpiMode.CUSTOM,
                source_requirements=spec.requirements,
                custom_resolver=explode,
            ),
        )
    )
    from atlanticus.operational_data.planner import DataRequirementPlanner

    failing_plan = DataRequirementPlanner().plan({item.key: item.requirements for item in failing})
    job = KpiRuntimeJob(
        catalog=failing,
        plan=failing_plan,
        loader=loader,
        persistence=persistence,
        source_watermarks=StaticWatermarkReader(watermark(10)),
    )

    result = job.run_iteration(RuntimeContextStub())
    batch = persistence.read_committed_after()[0]

    assert result.reason == 'evaluated'
    assert batch.evaluations[0].status.value == 'error'
    assert batch.evaluations[0].error == 'RuntimeError'
