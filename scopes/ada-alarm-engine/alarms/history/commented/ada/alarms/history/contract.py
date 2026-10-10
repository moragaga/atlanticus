from __future__ import annotations

import re
from datetime import UTC, date, datetime

from ada.contracts.alarms.history_projection import AlarmHistoryDomain, ProjectedAlarmHistoryFact
from atlanticus.datasets.core import (
    DatasetDefinition,
    DatasetKey,
    DatasetTarget,
    MaterializationDefinition,
    SingleArtifactLayout,
)

HISTORY_MATERIALIZATION = 'daily'
HISTORY_KEY_COLUMNS = ('historian_fact_id',)
HISTORY_ORDER_COLUMNS = ('event_at_utc', 'historian_fact_id')
HISTORY_PARTITION_DIMENSIONS = ('year', 'month', 'day')
_EVIDENCE_SEGMENT = re.compile(r'[A-Za-z0-9_]{1,120}')


# Error de contrato: nunca se corrige silenciosamente una identidad histórica defectuosa.
class AlarmHistoryContractError(ValueError):
    pass


_HISTORY_DEFINITIONS = {
    domain: DatasetDefinition(
        key=DatasetKey(namespace=('alarms', 'history'), name=domain.value),
        materializations=(
            MaterializationDefinition(
                name=HISTORY_MATERIALIZATION,
                layout=SingleArtifactLayout(),
                partition_dimensions=HISTORY_PARTITION_DIMENSIONS,
                route_segments=(),
            ),
        ),
        route_segments=('history', domain.value),
    )
    for domain in AlarmHistoryDomain
    if domain is not AlarmHistoryDomain.EVIDENCE
}


# Identifica un dataset diario compartido por todas las Rules del dominio.
def history_definition(domain: AlarmHistoryDomain) -> DatasetDefinition:
    if not isinstance(domain, AlarmHistoryDomain) or domain is AlarmHistoryDomain.EVIDENCE:
        raise AlarmHistoryContractError('History domain must be a non-evidence domain')
    return _HISTORY_DEFINITIONS[domain]


# Construye la ruta por familia y Rule sin modificar sus claves técnicas.
def evidence_definition(alarm_key: str) -> DatasetDefinition:
    family, rule = _evidence_identity(alarm_key)
    return DatasetDefinition(
        key=DatasetKey(namespace=('alarms', 'evidence', family), name=rule),
        materializations=(
            MaterializationDefinition(
                name=HISTORY_MATERIALIZATION,
                layout=SingleArtifactLayout(),
                partition_dimensions=HISTORY_PARTITION_DIMENSIONS,
                route_segments=(),
            ),
        ),
        route_segments=('evidence', family, rule),
    )


# Verifica identidad, día UTC y checksum antes de seleccionar una partición.
def history_destination(
    fact: ProjectedAlarmHistoryFact,
) -> tuple[DatasetDefinition, DatasetTarget]:
    if not isinstance(fact, ProjectedAlarmHistoryFact):
        raise TypeError('fact must be a ProjectedAlarmHistoryFact')
    if not isinstance(fact.domain, AlarmHistoryDomain):
        raise AlarmHistoryContractError('History domain is invalid')
    if (
        not isinstance(fact.day_utc, date)
        or isinstance(fact.day_utc, datetime)
        or not isinstance(fact.event_at_utc, datetime)
        or fact.event_at_utc.tzinfo is None
        or fact.event_at_utc.utcoffset() != UTC.utcoffset(fact.event_at_utc)
        or fact.day_utc != fact.event_at_utc.date()
    ):
        raise AlarmHistoryContractError('History day must match UTC event date')
    if (
        not isinstance(fact.historian_fact_id, str)
        or re.fullmatch(r'[0-9a-f]{64}', fact.historian_fact_id) is None
    ):
        raise AlarmHistoryContractError('History fact id must be a SHA-256 hex digest')
    definition = (
        evidence_definition(fact.alarm_key)
        if fact.domain is AlarmHistoryDomain.EVIDENCE
        else history_definition(fact.domain)
    )
    return definition, definition.resolve_target(
        materialization=HISTORY_MATERIALIZATION,
        partition=_daily_partition(fact.day_utc),
    )


# Representación canónica de la fecha UTC para los directorios físicos.
def _daily_partition(day: date) -> dict[str, str]:
    return {
        'year': f'{day.year:04d}',
        'month': f'{day.month:02d}',
        'day': f'{day.day:02d}',
    }


# Rechaza identidades ambiguas o inseguras para un directorio de Evidence.
def _evidence_identity(alarm_key: str) -> tuple[str, str]:
    if not isinstance(alarm_key, str):
        raise AlarmHistoryContractError('Evidence requires a canonical alarm key')
    family, separator, rule = alarm_key.partition('/')
    if (
        separator != '/'
        or _EVIDENCE_SEGMENT.fullmatch(family) is None
        or _EVIDENCE_SEGMENT.fullmatch(rule) is None
    ):
        raise AlarmHistoryContractError('Evidence key must be family/rule with safe segments')
    return family, rule
