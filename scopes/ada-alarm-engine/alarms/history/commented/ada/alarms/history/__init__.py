# Expone la interfaz de materialización de eventos y de episodios consolidados.
from ada.alarms.history.contract import (
    HISTORY_KEY_COLUMNS,
    HISTORY_ORDER_COLUMNS,
    HISTORY_PARTITION_DIMENSIONS,
    AlarmHistoryContractError,
    evidence_definition,
    history_definition,
    history_destination,
)
from ada.alarms.history.dataset import history_schema, history_table
from ada.alarms.history.episodes import episodes_schema, episodes_table
from ada.alarms.history.materializer import (
    AlarmHistoryMaterializationError,
    AlarmHistoryMaterializer,
    AlarmHistoryWriteResult,
)

__version__ = '1.0.0'

__all__ = [
    'HISTORY_KEY_COLUMNS',
    'HISTORY_ORDER_COLUMNS',
    'HISTORY_PARTITION_DIMENSIONS',
    'AlarmHistoryContractError',
    'AlarmHistoryMaterializationError',
    'AlarmHistoryMaterializer',
    'AlarmHistoryWriteResult',
    'episodes_schema',
    'episodes_table',
    'evidence_definition',
    'history_definition',
    'history_destination',
    'history_schema',
    'history_table',
]
