import ada.kpis.history as history


def test_public_api_is_explicit() -> None:
    assert set(history.__all__) == {
        'HISTORIAN_AUTHORITY_NAME',
        'HISTORIAN_AUTHORITY_NAMESPACE',
        'HISTORIAN_AUTHORITY_SCHEMA_VERSION',
        'HISTORY_KEY_COLUMNS',
        'HISTORY_MATERIALIZATION',
        'HISTORY_ORDER_COLUMNS',
        'HISTORY_PARTITION_DIMENSIONS',
        'HISTORY_SCHEMA_VERSION',
        'KpiHistorianAuthority',
        'KpiHistoryContractError',
        'KpiRollingMetadata',
        'ROLLING_DIRECTORY',
        'ROLLING_FILENAME',
        'ROLLING_GRID_SECONDS',
        'ROLLING_MAX_HOURS',
        'ROLLING_METADATA_KEY',
        'ROLLING_SCHEMA_VERSION',
        'ROLLING_TIMESTAMP_COLUMN',
        'ROLLING_VALUE_TYPES',
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
    }
    assert history.__version__ == '1.0.0'
