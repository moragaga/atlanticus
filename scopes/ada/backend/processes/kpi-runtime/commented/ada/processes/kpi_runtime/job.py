from __future__ import annotations

from ada.kpis.core import KpiCatalog, KpiWatermark
from ada.kpis.evaluation import evaluate_kpi
from ada.kpis.persistence import KpiEvaluationBatch, KpiPersistence
from ada.processes.kpi_runtime.errors import KpiRuntimeWatermarkError
from ada.processes.kpi_runtime.models import KpiRuntimeIterationResult, KpiRuntimeOutcome
from ada.processes.kpi_runtime.source_state import PiOperationalWatermarkReader

# Espejo pedagógico: conserva el comportamiento productivo y documenta la responsabilidad de este módulo.
from atlanticus.operational_data.core import DataSource
from atlanticus.operational_data.planner import DataLoadPlan
from atlanticus.operational_data.sources import DataSourceLoader
from atlanticus.runtime import JobRuntimeContext


class KpiRuntimeJob:
    def __init__(
        self,
        *,
        catalog: KpiCatalog,
        plan: DataLoadPlan,
        loader: DataSourceLoader,
        persistence: KpiPersistence,
        source_watermarks: PiOperationalWatermarkReader,
    ) -> None:
        if not isinstance(catalog, KpiCatalog):
            raise TypeError('catalog must be a KpiCatalog')
        if not isinstance(plan, DataLoadPlan):
            raise TypeError('plan must be a DataLoadPlan')
        if not isinstance(loader, DataSourceLoader):
            raise TypeError('loader must be a DataSourceLoader')
        if not isinstance(persistence, KpiPersistence):
            raise TypeError('persistence must be a KpiPersistence')
        if not callable(getattr(source_watermarks, 'current', None)):
            raise TypeError('source_watermarks must provide a callable current method')
        self._catalog = catalog
        self._plan = plan
        self._loader = loader
        self._persistence = persistence
        self._source_watermarks = source_watermarks

    def run_iteration(self, context: JobRuntimeContext) -> KpiRuntimeIterationResult:
        context.raise_if_cancelled()
        observed = self._source_watermarks.current()
        committed = self._persistence.committed_watermark()
        _record_before(context, observed=observed, committed=committed)
        if observed is None:
            return _empty(
                context,
                reason='source_watermark_missing',
                source_watermark=None,
                committed=committed,
            )
        if committed is not None and observed < committed:
            raise KpiRuntimeWatermarkError(
                'source watermark must not be older than the KPI committed watermark'
            )
        if observed == committed:
            return _empty(
                context,
                reason='up_to_date',
                source_watermark=observed,
                committed=committed,
            )
        if len(self._catalog) == 0:
            return _empty(
                context,
                reason='no_kpis_configured',
                source_watermark=observed,
                committed=committed,
            )

        loaded = self._loader.load(plan=self._plan, as_of=observed.timestamp_utc)
        source_traces = {
            DataSource.PI_INTERPOLATED: observed,
            DataSource.PI_RECORDED: observed,
        }
        evaluations = tuple(
            evaluate_kpi(
                spec=spec,
                context=loaded.context_for(spec.key),
                watermark=observed,
                source_watermarks=source_traces,
            )
            for spec in self._catalog
        )
        batch = KpiEvaluationBatch(watermark=observed, evaluations=evaluations)
        context.raise_if_cancelled()
        context.assert_lease_current()
        with context.fenced_mutation():
            commit = self._persistence.commit(batch)
        context.mark_iteration_work()
        context.increment_execution_counter('evaluations_committed')
        _record_after(
            context,
            observed=observed,
            before=commit.before,
            after=commit.after,
            write_status=commit.write_status.value,
            evaluation_count=len(evaluations),
        )
        return KpiRuntimeIterationResult(
            outcome=KpiRuntimeOutcome.COMPLETED,
            reason='evaluated',
            source_watermark=observed,
            committed_before=commit.before,
            committed_after=commit.after,
            evaluation_write_status=commit.write_status,
            evaluation_count=len(evaluations),
        )


def _empty(
    context: JobRuntimeContext,
    *,
    reason: str,
    source_watermark: KpiWatermark | None,
    committed: KpiWatermark | None,
) -> KpiRuntimeIterationResult:
    context.set_iteration_fact('outcome', KpiRuntimeOutcome.EMPTY.value)
    context.set_iteration_fact('reason', reason)
    context.set_iteration_fact(
        'kpi_committed_before_utc', None if committed is None else committed.to_text()
    )
    context.set_iteration_fact(
        'kpi_committed_after_utc', None if committed is None else committed.to_text()
    )
    return KpiRuntimeIterationResult(
        outcome=KpiRuntimeOutcome.EMPTY,
        reason=reason,
        source_watermark=source_watermark,
        committed_before=committed,
        committed_after=committed,
    )


def _record_before(
    context: JobRuntimeContext,
    *,
    observed: KpiWatermark | None,
    committed: KpiWatermark | None,
) -> None:
    source = None if observed is None else observed.to_text()
    current = None if committed is None else committed.to_text()
    context.set_iteration_fact('pi_observed_watermark_utc', source)
    context.set_iteration_fact('kpi_committed_before_utc', current)
    context.set_execution_fact('pi_observed_watermark_utc', source)
    context.set_execution_fact('kpi_committed_watermark_utc', current)


def _record_after(
    context: JobRuntimeContext,
    *,
    observed: KpiWatermark,
    before: KpiWatermark | None,
    after: KpiWatermark,
    write_status: str,
    evaluation_count: int,
) -> None:
    context.set_iteration_fact('outcome', KpiRuntimeOutcome.COMPLETED.value)
    context.set_iteration_fact('reason', 'evaluated')
    context.set_iteration_fact('pi_watermark_utc', observed.to_text())
    context.set_iteration_fact(
        'kpi_committed_before_utc', None if before is None else before.to_text()
    )
    context.set_iteration_fact('kpi_committed_after_utc', after.to_text())
    context.set_iteration_fact('evaluation_write_status', write_status)
    context.set_iteration_fact('evaluation_count', evaluation_count)
    context.set_execution_fact('kpi_committed_watermark_utc', after.to_text())
