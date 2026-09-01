# Superficie pública única del contrato compartido de historial KPI.
from ada.kpis.history.contract import (
    HISTORY_KEY_COLUMNS,
    HISTORY_MATERIALIZATION,
    HISTORY_ORDER_COLUMNS,
    HISTORY_PARTITION_DIMENSIONS,
    HISTORY_SCHEMA_VERSION,
    error_history_definition,
    error_history_schema,
    error_history_target,
    history_definition,
    history_schema,
    history_target,
)
from ada.kpis.history.encoding import decode_history_value, encode_history_value
from ada.kpis.history.errors import KpiHistoryContractError
from ada.kpis.history.revision import historian_revision, historian_watermark_text

__version__ = '1.0.0'

__all__ = [
    'HISTORY_KEY_COLUMNS',
    'HISTORY_MATERIALIZATION',
    'HISTORY_ORDER_COLUMNS',
    'HISTORY_PARTITION_DIMENSIONS',
    'HISTORY_SCHEMA_VERSION',
    'KpiHistoryContractError',
    '__version__',
    'decode_history_value',
    'encode_history_value',
    'error_history_definition',
    'error_history_schema',
    'error_history_target',
    'historian_revision',
    'historian_watermark_text',
    'history_definition',
    'history_schema',
    'history_target',
]
