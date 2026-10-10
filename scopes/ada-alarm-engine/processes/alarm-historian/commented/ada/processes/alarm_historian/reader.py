# Lectura incremental: se limita el número de registros FACTS, no el número de hechos proyectados.
# No se persiste la posición aquí; corresponde al job después de materializar el lote.
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
from pathlib import Path

from ada.contracts.alarms.facts_stream import FactsStreamPosition, iter_committed_facts
from ada.contracts.alarms.history_projection import (
    ProjectedAlarmHistoryFact,
    project_committed_alarm_facts,
)


@dataclass(frozen=True, slots=True)
class AlarmHistorianBatch:
    facts: tuple[ProjectedAlarmHistoryFact, ...]
    excluded_count: int
    records_read: int
    last_position: FactsStreamPosition | None


class AlarmHistorianReader:
    def __init__(self, *, facts_root: Path, stream_id: str, max_records: int) -> None:
        if not isinstance(facts_root, Path) or not facts_root.is_absolute():
            raise ValueError('FACTS root must be an absolute Path')
        if not isinstance(stream_id, str) or not stream_id or stream_id != stream_id.strip():
            raise ValueError('stream_id must be non-empty normalized text')
        if isinstance(max_records, bool) or not isinstance(max_records, int) or max_records <= 0:
            raise ValueError('max_records must be a positive integer')
        self._facts_root = facts_root
        self._stream_id = stream_id
        self._max_records = max_records

    def read(self, *, after: FactsStreamPosition | None) -> AlarmHistorianBatch:
        projected: list[ProjectedAlarmHistoryFact] = []
        excluded = 0
        count = 0
        position = after
        for committed in islice(
            iter_committed_facts(root=self._facts_root, after=after), self._max_records
        ):
            projection = project_committed_alarm_facts(facts=committed, stream_id=self._stream_id)
            projected.extend(projection.facts)
            excluded += len(projection.excluded)
            count += 1
            position = committed.position
        return AlarmHistorianBatch(
            facts=tuple(projected),
            excluded_count=excluded,
            records_read=count,
            last_position=position,
        )
