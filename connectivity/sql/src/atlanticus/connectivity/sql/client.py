"""Cliente SQL síncrono de sólo lectura pública y memoria acotada."""

from __future__ import annotations

import re
import warnings
from collections.abc import Iterator, Mapping, Sequence
from importlib import import_module
from time import perf_counter
from typing import Any

from atlanticus.connectivity.sql.errors import (
    SqlConfigurationError,
    SqlConnectionError,
    SqlError,
    SqlQueryContractError,
    SqlQueryError,
    SqlResultLimitError,
    SqlTimeoutError,
)
from atlanticus.connectivity.sql.models import SqlBatch, SqlResult, SqlTimeoutPhase
from atlanticus.connectivity.sql.settings import (
    SqlSettings,
    _prepare_mssql_connection,
    require_positive_integer,
)
from atlanticus.observability import ErrorInfo, ResultSummary, runtime_guard

_COMPONENT = 'atlanticus.connectivity.sql'
_TIMEOUT_STATES = frozenset({'HYT00', 'HYT01'})
_SQLSTATE_PATTERN = re.compile(r'\b([A-Z0-9]{5})\b')


def _safe_parameters(args: tuple[Any, ...], values: Mapping[str, Any]) -> Mapping[str, Any]:
    instance = args[0] if args else None
    settings = getattr(instance, 'settings', None)
    safe: dict[str, Any] = {}
    if isinstance(settings, SqlSettings) and settings.suffix is not None:
        safe['configuration_suffix'] = settings.suffix
    parameters = values.get('parameters')
    if parameters is not None and not isinstance(parameters, str | bytes | Mapping):
        try:
            safe['parameter_count'] = len(parameters)
        except TypeError:
            pass
    for name in ('batch_size', 'max_rows'):
        value = values.get(name)
        if value is not None:
            safe[name] = value
    return safe


def _safe_error(error: BaseException) -> ErrorInfo:
    message = str(error) if isinstance(error, SqlError | TypeError) else 'SQL operation failed'
    return ErrorInfo(error_type=type(error).__name__, message=message)


def _query_result(value: Any) -> ResultSummary:
    if not isinstance(value, SqlResult):
        return ResultSummary()
    return ResultSummary(
        attributes={'column_count': len(value.columns)},
        metrics={'row_count': value.row_count},
    )


class SqlBatchStream(Iterator[SqlBatch]):
    """Iterador cerrable que mantiene una sola conexión durante una consulta grande."""

    def __init__(
        self,
        *,
        connection: Any,
        cursor: Any,
        driver_error_type: type[BaseException],
        columns: tuple[str, ...],
        batch_size: int,
    ) -> None:
        self._connection = connection
        self._cursor = cursor
        self._driver_error_type = driver_error_type
        self._columns = columns
        self._batch_size = batch_size
        self._batch_number = 0
        self._row_offset = 0
        self._closed = False

    def __enter__(self) -> SqlBatchStream:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: object | None,
    ) -> None:
        try:
            self.close()
        except SqlConnectionError:
            if exception_type is None:
                raise

    def __iter__(self) -> SqlBatchStream:
        return self

    def __next__(self) -> SqlBatch:
        if self._closed:
            raise StopIteration
        started_at = perf_counter()
        try:
            fetched = self._cursor.fetchmany(self._batch_size)
        except self._driver_error_type as error:
            self._close_without_error()
            raise _database_error(error, phase=SqlTimeoutPhase.QUERY) from None
        except Exception:
            self._close_without_error()
            raise SqlQueryError('SQL batch read failed') from None
        if not fetched:
            self.close()
            raise StopIteration
        rows = tuple(tuple(row) for row in fetched)
        self._batch_number += 1
        batch = SqlBatch(
            columns=self._columns,
            rows=rows,
            batch_number=self._batch_number,
            row_offset=self._row_offset,
            duration_ms=round((perf_counter() - started_at) * 1000, 4),
        )
        self._row_offset += batch.row_count
        return batch

    def close(self) -> None:
        """Cierra cursor y conexión de forma idempotente."""

        if self._closed:
            return
        self._closed = True
        cursor_error = _close_resource(self._cursor)
        connection_error = _close_resource(self._connection)
        if cursor_error or connection_error:
            raise SqlConnectionError('Could not close SQL batch stream') from None

    def _close_without_error(self) -> None:
        if self._closed:
            return
        self._closed = True
        _close_resource(self._cursor)
        _close_resource(self._connection)

    def __del__(self) -> None:
        try:
            self._close_without_error()
        except Exception:
            pass


class SqlClient:
    """Ejecuta consultas parametrizadas sin conocer tablas ni reglas de negocio."""

    def __init__(self, *, settings: SqlSettings) -> None:
        if not isinstance(settings, SqlSettings):
            raise SqlConfigurationError('settings must be SqlSettings')
        self.settings = settings

    @runtime_guard(
        operation='sql.health_check',
        component=_COMPONENT,
        parameter_mapper=_safe_parameters,
        error_mapper=_safe_error,
    )
    def health_check(self) -> bool:
        """Comprueba conexión y una consulta mínima mediante un único intento."""

        result = self._query_impl(
            statement='SELECT CAST(1 AS INTEGER) AS health',
            parameters=(),
            max_rows=1,
        )
        return result.rows == ((1,),)

    @runtime_guard(
        operation='sql.query',
        component=_COMPONENT,
        parameter_mapper=_safe_parameters,
        result_mapper=_query_result,
        error_mapper=_safe_error,
    )
    def query(
        self,
        statement: str,
        parameters: Sequence[Any] | None = None,
        *,
        max_rows: int | None = None,
    ) -> SqlResult:
        """Materializa un resultado pequeño con un límite estricto de filas."""

        normalized_max_rows = (
            self.settings.max_query_rows
            if max_rows is None
            else require_positive_integer(max_rows, 'max_rows')
        )
        return self._query_impl(
            statement=statement,
            parameters=_normalize_parameters(parameters),
            max_rows=normalized_max_rows,
        )

    @runtime_guard(
        operation='sql.iter_batches',
        component=_COMPONENT,
        parameter_mapper=_safe_parameters,
        error_mapper=_safe_error,
    )
    def iter_batches(
        self,
        statement: str,
        parameters: Sequence[Any] | None = None,
        *,
        batch_size: int | None = None,
    ) -> SqlBatchStream:
        """Abre una lectura por ``fetchmany()`` y entrega un stream cerrable."""

        normalized_statement = _normalize_statement(statement)
        normalized_parameters = _normalize_parameters(parameters)
        normalized_batch_size = (
            self.settings.batch_size
            if batch_size is None
            else require_positive_integer(batch_size, 'batch_size')
        )
        connection, driver_error_type = self._connect()
        cursor: Any | None = None
        try:
            cursor = connection.cursor()
            _execute(cursor, normalized_statement, normalized_parameters)
            columns = _read_columns(cursor)
        except SqlError:
            if cursor is not None:
                _close_resource(cursor)
            _close_resource(connection)
            raise
        except driver_error_type as error:
            if cursor is not None:
                _close_resource(cursor)
            _close_resource(connection)
            raise _database_error(error, phase=SqlTimeoutPhase.QUERY) from None
        except Exception:
            if cursor is not None:
                _close_resource(cursor)
            _close_resource(connection)
            raise SqlQueryError('SQL query failed') from None
        return SqlBatchStream(
            connection=connection,
            cursor=cursor,
            driver_error_type=driver_error_type,
            columns=columns,
            batch_size=normalized_batch_size,
        )

    def _query_impl(
        self,
        *,
        statement: str,
        parameters: Sequence[Any],
        max_rows: int,
    ) -> SqlResult:
        normalized_statement = _normalize_statement(statement)
        normalized_parameters = _normalize_parameters(parameters)
        started_at = perf_counter()
        connection, driver_error_type = self._connect()
        cursor: Any | None = None
        result: SqlResult | None = None
        operation_error: BaseException | None = None
        try:
            cursor = connection.cursor()
            _execute(cursor, normalized_statement, normalized_parameters)
            columns = _read_columns(cursor)
            fetched = cursor.fetchmany(max_rows + 1)
            if len(fetched) > max_rows:
                raise SqlResultLimitError(max_rows=max_rows)
            result = SqlResult(
                columns=columns,
                rows=tuple(tuple(row) for row in fetched),
                duration_ms=round((perf_counter() - started_at) * 1000, 4),
            )
        except SqlError as error:
            operation_error = error
        except driver_error_type as error:
            operation_error = _database_error(error, phase=SqlTimeoutPhase.QUERY)
        except Exception:
            operation_error = SqlQueryError('SQL query failed')
        cursor_error = _close_resource(cursor)
        connection_error = _close_resource(connection)
        if operation_error is not None:
            raise operation_error from None
        if cursor_error or connection_error:
            raise SqlConnectionError('Could not close SQL connection') from None
        if result is None:
            raise SqlQueryError('SQL query failed')
        return result

    def _connect(self) -> tuple[Any, type[BaseException]]:
        driver = _load_mssql_driver()
        connection: Any | None = None
        try:
            connection_string, connection_timeout_seconds = _prepare_mssql_connection(
                self.settings.connection_string
            )
            connection = driver.connect(
                connection_string,
                autocommit=True,
                timeout=0 if connection_timeout_seconds is None else connection_timeout_seconds,
                native_uuid=False,
            )
            connection.timeout = self.settings.query_timeout_seconds
            return connection, driver.Error
        except driver.Error as error:
            _close_resource(connection)
            raise _database_error(error, phase=SqlTimeoutPhase.CONNECT) from None
        except Exception:
            _close_resource(connection)
            raise SqlConnectionError('Could not open SQL connection') from None


def _normalize_statement(value: str) -> str:
    if not isinstance(value, str):
        raise SqlQueryContractError('statement must be a string')
    normalized = value.strip()
    if not normalized:
        raise SqlQueryContractError('statement must not be empty')
    if '\x00' in normalized:
        raise SqlQueryContractError('statement must not contain null characters')
    return normalized


def _normalize_parameters(value: Sequence[Any] | None) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, str | bytes | bytearray | memoryview | Mapping):
        raise SqlQueryContractError('parameters must be a positional sequence')
    try:
        return tuple(value)
    except TypeError:
        raise SqlQueryContractError('parameters must be a positional sequence') from None


def _execute(cursor: Any, statement: str, parameters: Sequence[Any]) -> None:
    if parameters:
        cursor.execute(statement, *parameters)
    else:
        cursor.execute(statement)


def _read_columns(cursor: Any) -> tuple[str, ...]:
    description = cursor.description
    if not description:
        raise SqlQueryContractError('SQL statement did not produce a result set')
    columns = tuple(str(column[0]) for column in description)
    if any(not column.strip() for column in columns):
        raise SqlQueryError('SQL result contains an unnamed column')
    return columns


def _database_error(error: BaseException, *, phase: SqlTimeoutPhase) -> SqlError:
    if _is_timeout(error):
        return SqlTimeoutError(phase=phase)
    if phase is SqlTimeoutPhase.CONNECT:
        return SqlConnectionError('Could not open SQL connection')
    return SqlQueryError('SQL query failed')


def _is_timeout(error: BaseException) -> bool:
    values = [*error.args]
    values.extend(getattr(error, name, None) for name in ('driver_error', 'ddbc_error', 'message'))
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip().upper()
        if normalized in _TIMEOUT_STATES:
            return True
        match = _SQLSTATE_PATTERN.search(normalized)
        if match is not None and match.group(1) in _TIMEOUT_STATES:
            return True
        if 'TIMEOUT' in normalized or 'TIMED OUT' in normalized:
            return True
    return False


def _close_resource(resource: Any | None) -> bool:
    if resource is None:
        return False
    close = getattr(resource, 'close', None)
    if not callable(close):
        return False
    try:
        close()
    except Exception:
        return True
    return False


def _load_mssql_driver() -> Any:
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                'ignore',
                message=r"'return' in a 'finally' block",
                category=SyntaxWarning,
            )
            return import_module('mssql_python')
    except (ImportError, OSError):
        raise SqlConnectionError('SQL driver runtime is unavailable') from None
