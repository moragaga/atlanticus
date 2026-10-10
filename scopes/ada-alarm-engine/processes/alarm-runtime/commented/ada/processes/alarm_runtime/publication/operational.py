from __future__ import annotations

from dataclasses import dataclass, field

from ada.alarms.persistence.operational import (
    AlarmPersistence,
    AlarmRecoveryRequiredError,
    JournalPosition,
)
from ada.processes.alarm_runtime.publication.output_batches import (
    AlarmCommittedFactsExporter,
    FactsExportContext,
)
from ada.processes.alarm_runtime.publication.output_current import AlarmDurableCurrentPublisher


@dataclass(slots=True)
class AlarmDurablePublications:
    persistence: AlarmPersistence
    facts: AlarmCommittedFactsExporter
    current: AlarmDurableCurrentPublisher
    _initialized: bool = field(default=False, init=False, repr=False)
    _last_reconciled: JournalPosition | None = field(default=None, init=False, repr=False)
    _facts_initialized: bool = field(default=False, init=False, repr=False)
    _last_facts_reconciled: JournalPosition | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.persistence, AlarmPersistence):
            raise TypeError('publication persistence must be AlarmPersistence')
        if not isinstance(self.facts, AlarmCommittedFactsExporter):
            raise TypeError('facts publisher must be AlarmCommittedFactsExporter')
        if not isinstance(self.current, AlarmDurableCurrentPublisher):
            raise TypeError('current publisher must be AlarmDurableCurrentPublisher')
        if (
            self.facts.root != self.current.root
            or self.facts.source_key != self.current.source_key
        ):
            raise ValueError('durable publications must share output root and source_key')

    # CURRENT puede actualizarse por iteración; FACTS mantiene un watermark independiente.
    def reconcile(
        self, context: FactsExportContext, *, force: bool = False, publish_facts: bool = True
    ) -> bool:
        context.assert_lease_current()
        head = self.persistence.read_head()
        if not head.aligned:
            raise AlarmRecoveryRequiredError('durable publications require aligned WAL recovery')
        # Se calculan necesidades de publicación sin forzar ambas proyecciones en cada ciclo.
        need_current = force or not self._initialized or self._last_reconciled != head.durable
        need_facts = publish_facts and (
            force or not self._facts_initialized or self._last_facts_reconciled != head.durable
        )
        if not need_current and not need_facts:
            return False
        exported = 0
        if need_facts:
            self.facts.initialize_if_needed(context=context, persistence=self.persistence)
            exported = self.facts.publish_unexported(context=context, persistence=self.persistence)
        changed = False
        if need_current:
            effective = self.persistence.read_effective_head()
            if effective is not None:
                changed = self.current.publish(context=context, persistence=self.persistence)
            elif head.durable is not None:
                raise AlarmRecoveryRequiredError('durable journal has no EFFECTIVE configuration')
        context.assert_lease_current()
        if self.persistence.read_head() != head:
            raise AlarmRecoveryRequiredError('durable journal changed during publication')
        if need_current:
            self._last_reconciled = head.durable
            self._initialized = True
        if need_facts:
            self._last_facts_reconciled = head.durable
            self._facts_initialized = True
        return exported > 0 or changed
