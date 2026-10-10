from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from ada.alarms.history.contract import (
    HISTORY_KEY_COLUMNS,
    HISTORY_ORDER_COLUMNS,
    history_destination,
)
from ada.alarms.history.dataset import history_table
from ada.contracts.alarms.history_projection import ProjectedAlarmHistoryFact
from atlanticus.datasets.core import (
    DatasetDefinition,
    DatasetTarget,
    PublicationQuality,
    PublicationStatus,
)


class AlarmHistoryMaterializationError(ValueError):
    pass


class _DatasetMerger(Protocol):
    def merge(self, **kwargs): ...


@dataclass(frozen=True, slots=True)
class AlarmHistoryWriteResult:
    facts_received: int
    facts_unique: int
    targets_processed: int
    targets_committed: int
    targets_unchanged: int
    target_identifiers: tuple[str, ...]


class AlarmHistoryMaterializer:
    def __init__(self, *, runtime: _DatasetMerger) -> None:
        if not callable(getattr(runtime, 'merge', None)):
            raise TypeError('runtime must provide a callable merge method')
        self._runtime = runtime

    def materialize(
        self,
        *,
        facts: Iterable[ProjectedAlarmHistoryFact],
        check_current: Callable[[], None] | None = None,
    ) -> AlarmHistoryWriteResult:
        if isinstance(facts, ProjectedAlarmHistoryFact | str | bytes):
            raise TypeError('facts must be an iterable of projected history facts')
        if check_current is not None and not callable(check_current):
            raise TypeError('check_current must be callable or None')
        try:
            iterator = iter(facts)
        except TypeError as error:
            raise TypeError('facts must be an iterable of projected history facts') from error
        groups: dict[
            str, tuple[DatasetDefinition, DatasetTarget, list[ProjectedAlarmHistoryFact]]
        ] = {}
        observed: dict[str, ProjectedAlarmHistoryFact] = {}
        received = 0
        _check_current(check_current)
        for fact in iterator:
            _check_current(check_current)
            definition, target = history_destination(fact)
            received += 1
            prior = observed.get(fact.historian_fact_id)
            if prior is not None:
                if prior != fact:
                    raise AlarmHistoryMaterializationError(
                        'History fact identity maps to conflicting content'
                    )
                continue
            observed[fact.historian_fact_id] = fact
            if target.identifier not in groups:
                groups[target.identifier] = (definition, target, [])
            groups[target.identifier][2].append(fact)
        committed = 0
        unchanged = 0
        targets: list[str] = []
        for identifier, (definition, target, rows) in sorted(groups.items()):
            _check_current(check_current)
            rows.sort(key=lambda item: (item.event_at_utc, item.historian_fact_id))
            publication = self._runtime.merge(
                definition=definition,
                target=target,
                data=history_table(rows),
                key_columns=HISTORY_KEY_COLUMNS,
                order_by=HISTORY_ORDER_COLUMNS,
            )
            if (
                publication.target != target
                or publication.status not in {PublicationStatus.COMMITTED, PublicationStatus.UNCHANGED}
                or publication.quality is not PublicationQuality.SUCCESS
            ):
                raise AlarmHistoryMaterializationError(
                    'History destination did not confirm a successful publication'
                )
            if publication.status is PublicationStatus.COMMITTED:
                committed += 1
            else:
                unchanged += 1
            targets.append(identifier)
        _check_current(check_current)
        return AlarmHistoryWriteResult(
            facts_received=received,
            facts_unique=len(observed),
            targets_processed=len(targets),
            targets_committed=committed,
            targets_unchanged=unchanged,
            target_identifiers=tuple(targets),
        )


def _check_current(check_current: Callable[[], None] | None) -> None:
    if check_current is not None:
        check_current()
