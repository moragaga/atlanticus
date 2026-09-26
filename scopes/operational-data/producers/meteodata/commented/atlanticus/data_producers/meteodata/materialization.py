from __future__ import annotations

# Las publicaciones se hacen con DatasetRuntime; daily tiene particiones por fecha UTC y merge que preserva las columnas anteriores.

from collections import defaultdict
from datetime import datetime
from typing import Any

import pyarrow as pa

from atlanticus.data_producers.meteodata.consolidation import consolidate
from atlanticus.data_producers.meteodata.models import Measurement, Projection
from atlanticus.datasets.layouts import SingleArtifactLayout
from atlanticus.datasets.models import DatasetDefinition, DatasetKey, MaterializationDefinition
from atlanticus.datasets.runtime import DatasetRuntime, DatasetRuntimeNotFoundError
from atlanticus.runtime import JobRuntimeContext

PROJECTION_DATASET = DatasetDefinition(
    key=DatasetKey(namespace=('meteodata',), name='proyeccion'),
    materializations=(MaterializationDefinition(name='latest', layout=SingleArtifactLayout()),),
)
DATA_DATASET = DatasetDefinition(
    key=DatasetKey(namespace=('meteodata',), name='datos'),
    materializations=(
        MaterializationDefinition(
            name='daily',
            layout=SingleArtifactLayout(),
            partition_dimensions=('year', 'month', 'day'),
        ),
    ),
)
PROJECTION_SCHEMA = pa.schema(
    [
        pa.field('timestamp', pa.timestamp('us', tz='UTC'), nullable=False),
        pa.field('promedio_dia_mp10', pa.float64()),
        pa.field('proyeccion_mp10', pa.float64()),
        pa.field('monitoreo_oficial', pa.bool_()),
    ]
)
DATA_SCHEMA = pa.schema(
    [
        pa.field('timestamp', pa.timestamp('us', tz='UTC'), nullable=False),
        pa.field('mp10', pa.float64()),
        pa.field('vel', pa.float64()),
        pa.field('dir', pa.float64()),
        pa.field('estacion_mp10', pa.string()),
    ]
)


class MeteodataMaterializer:
    def __init__(self, *, runtime: DatasetRuntime) -> None:
        self.runtime = runtime

    def publish_projection(self, *, projection: Projection, context: JobRuntimeContext) -> bool:
        target = PROJECTION_DATASET.resolve_target(materialization='latest')
        row = {
            'timestamp': projection.timestamp,
            'promedio_dia_mp10': projection.promedio_dia_mp10,
            'proyeccion_mp10': projection.proyeccion_mp10,
            'monitoreo_oficial': projection.monitoreo_oficial,
        }
        try:
            previous = self.runtime.read_table(definition=PROJECTION_DATASET, target=target).table
        except DatasetRuntimeNotFoundError:
            previous = None
        if previous is not None and previous.to_pylist() == [row]:
            return False
        context.raise_if_cancelled()
        self.runtime.replace(
            definition=PROJECTION_DATASET,
            target=target,
            data=pa.Table.from_pylist([row], schema=PROJECTION_SCHEMA),
        )
        return True

    def publish_data(
        self,
        *,
        measurements: tuple[Measurement, ...],
        context: JobRuntimeContext,
    ) -> int:
        grouped: dict[tuple[str, str, str], list[Measurement]] = defaultdict(list)
        for sample in measurements:
            timestamp = sample.timestamp
            grouped[(timestamp.strftime('%Y'), timestamp.strftime('%m'), timestamp.strftime('%d'))].append(sample)
        changed = 0
        for (year, month, day), samples in sorted(grouped.items()):
            context.raise_if_cancelled()
            target = DATA_DATASET.resolve_target(
                materialization='daily',
                partition={'year': year, 'month': month, 'day': day},
            )
            try:
                previous = self.runtime.read_table(definition=DATA_DATASET, target=target).table
            except DatasetRuntimeNotFoundError:
                previous = None
            existing: dict[datetime, dict[str, Any]] = {}
            if previous is not None:
                if previous.schema != DATA_SCHEMA:
                    raise ValueError('existing Meteodata daily dataset schema is incompatible')
                existing = {row['timestamp']: row for row in previous.to_pylist()}
            updated = consolidate(existing=existing, measurements=samples)
            if not updated:
                continue
            table = pa.Table.from_pylist(
                [updated[timestamp] for timestamp in sorted(updated)],
                schema=DATA_SCHEMA,
            )
            context.raise_if_cancelled()
            self.runtime.merge(
                definition=DATA_DATASET,
                target=target,
                data=table,
                key_columns=('timestamp',),
                order_by=('timestamp',),
            )
            changed += table.num_rows
        return changed
