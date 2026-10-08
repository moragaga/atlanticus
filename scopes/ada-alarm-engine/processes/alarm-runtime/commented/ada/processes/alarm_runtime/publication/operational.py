# Orquesta publicaciones durables sin intervenir en evaluación, lifecycle ni commits.
# El checkpoint histórico de FACTS y el documento agregado CURRENT siguen separados.
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
    # Este marcador local solo evita lecturas completas cuando no cambió el WAL.
    # No es durable: cada nuevo proceso vuelve a reconciliar ambas salidas.
    _initialized: bool = field(default=False, init=False, repr=False)
    _last_reconciled: JournalPosition | None = field(default=None, init=False, repr=False)

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

    def reconcile(self, context: FactsExportContext, *, force: bool = False) -> bool:
        context.assert_lease_current()
        head = self.persistence.read_head()
        # Jamás publicamos contra un WAL cuyo materializado quedó por detrás del durable.
        if not head.aligned:
            raise AlarmRecoveryRequiredError('durable publications require aligned WAL recovery')
        if not force and self._initialized and self._last_reconciled == head.durable:
            return False
        # FACTS avanza su propio cursor; un reintento tras un fallo no repite lotes.
        self.facts.initialize_if_needed(context=context, persistence=self.persistence)
        exported = self.facts.publish_unexported(context=context, persistence=self.persistence)
        effective = self.persistence.read_effective_head()
        changed = False
        # Sin EFFECTIVE no fabricamos un CURRENT aparentemente vacío y válido.
        if effective is not None:
            changed = self.current.publish(context=context, persistence=self.persistence)
        elif head.durable is not None:
            raise AlarmRecoveryRequiredError('durable journal has no EFFECTIVE configuration')
        context.assert_lease_current()
        # El marcador de éxito se publica únicamente cuando terminaron las dos salidas.
        if self.persistence.read_head() != head:
            raise AlarmRecoveryRequiredError('durable journal changed during publication')
        self._last_reconciled = head.durable
        self._initialized = True
        return exported > 0 or changed
