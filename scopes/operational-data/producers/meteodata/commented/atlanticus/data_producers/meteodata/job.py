from __future__ import annotations

# El job aísla proyección y mediciones. Reintenta los datos únicamente cuando no hay nuevas filas o correcciones.

from datetime import UTC, datetime

from atlanticus.connectivity.http import HttpError
from atlanticus.data_producers.meteodata.acquisition import MeteodataAcquirer
from atlanticus.data_producers.meteodata.errors import (
    MeteodataAcquisitionError,
    MeteodataResponseError,
)
from atlanticus.data_producers.meteodata.materialization import MeteodataMaterializer
from atlanticus.datasets.runtime import DatasetRuntimeError
from atlanticus.runtime import JobRuntimeContext


class MeteodataJob:
    def __init__(
        self,
        *,
        acquirer: MeteodataAcquirer,
        materializer: MeteodataMaterializer,
        lookback_minutes: int,
        retry_delay_seconds: int,
    ) -> None:
        self.acquirer = acquirer
        self.materializer = materializer
        self.lookback_minutes = lookback_minutes
        self.retry_delay_seconds = retry_delay_seconds

    def run_iteration(self, context: JobRuntimeContext) -> None:
        context.raise_if_cancelled()
        projection_error = False
        data_error = False
        projection_updated = False
        data_rows_updated = 0
        data_retried = False
        failed_queries: tuple[str, ...] = ()
        try:
            projection = self.acquirer.acquire_projection()
            projection_updated = self.materializer.publish_projection(
                projection=projection,
                context=context,
            )
        except (HttpError, MeteodataResponseError, DatasetRuntimeError) as error:
            projection_error = True
            context.logger.warning(
                'Meteodata projection acquisition or publication failed',
                event_name='meteodata.projection.failed',
                error_type=type(error).__name__,
            )
        try:
            batch = self.acquirer.acquire_data(
                now_utc=datetime.now(UTC),
                lookback_minutes=self.lookback_minutes,
                check_cancelled=context.raise_if_cancelled,
            )
            failed_queries = batch.failed_queries
            data_rows_updated = self.materializer.publish_data(
                measurements=batch.measurements,
                context=context,
            )
            if data_rows_updated == 0 and self.retry_delay_seconds:
                context.raise_if_cancelled()
                if context.safe_remaining_seconds > self.retry_delay_seconds + 90:
                    if context.wait(self.retry_delay_seconds):
                        context.raise_if_cancelled()
                        data_retried = True
                        retry = self.acquirer.acquire_data(
                            now_utc=datetime.now(UTC),
                            lookback_minutes=self.lookback_minutes,
                            check_cancelled=context.raise_if_cancelled,
                        )
                        failed_queries = retry.failed_queries
                        data_rows_updated = self.materializer.publish_data(
                            measurements=retry.measurements,
                            context=context,
                        )
            if failed_queries:
                context.logger.warning(
                    'Some Meteodata measurement queries failed',
                    event_name='meteodata.data.partial',
                    failed_queries=tuple(sorted(set(failed_queries))),
                )
        except (HttpError, MeteodataResponseError, MeteodataAcquisitionError, DatasetRuntimeError) as error:
            data_error = True
            context.logger.warning(
                'Meteodata measurements acquisition or publication failed',
                event_name='meteodata.data.failed',
                error_type=type(error).__name__,
            )
        context.set_iteration_fact('projection_updated', projection_updated)
        context.set_iteration_fact('data_rows_updated', data_rows_updated)
        context.set_iteration_fact('data_retried', data_retried)
        context.set_iteration_fact('failed_queries', len(failed_queries))
        context.set_iteration_fact('projection_failed', projection_error)
        context.set_iteration_fact('data_failed', data_error)
        context.set_iteration_fact('outcome', 'partial' if projection_error or data_error or failed_queries else 'completed')
        if projection_updated or data_rows_updated:
            context.mark_iteration_work()
        if projection_error and data_error:
            raise MeteodataAcquisitionError('both Meteodata publication streams failed')
