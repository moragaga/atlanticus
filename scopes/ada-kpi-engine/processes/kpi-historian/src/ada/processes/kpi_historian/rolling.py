from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Protocol

from ada.kpis.core import KpiStatus, KpiValueKind, KpiWatermark
from ada.kpis.history import (
    ROLLING_DIRECTORY,
    ROLLING_FILENAME,
    ROLLING_GRID_SECONDS,
    ROLLING_MAX_HOURS,
    ROLLING_VALUE_TYPES,
    KpiHistorianAuthority,
    KpiHistoryContractError,
    KpiRollingMetadata,
    history_definition,
    history_target,
)
from ada.kpis.history.dataset import (
    history_records_from_table,
    rolling_definition,
    rolling_state_from_table,
    rolling_table,
    rolling_target,
)
from ada.kpis.persistence import KpiEvaluationBatch
from ada.processes.kpi_historian.errors import KpiHistorianRollingError
from atlanticus.datasets.runtime import (
    ColumnFilter,
    DatasetRuntimeNotFoundError,
    DatasetRuntimeReadError,
    DatasetRuntimeValidationError,
    DatasetRuntimeWriteError,
    FilterOperator,
)


class _HistoryRuntime(Protocol):
    def scan_table(self, **kwargs): ...


class _RollingRuntime(Protocol):
    def read_table(self, **kwargs): ...

    def replace(self, **kwargs): ...


@dataclass(slots=True)
class _RollingState:
    metadata: KpiRollingMetadata
    points: dict[datetime, dict[str, str]]
    value_types: dict[str, str]


def rolling_path(application_root: Path) -> Path:
    if not isinstance(application_root, Path):
        raise TypeError('application_root must be Path')
    return application_root / ROLLING_DIRECTORY / ROLLING_FILENAME


class KpiHistorianRollingMaterializer:
    def __init__(
        self,
        *,
        history_runtime: _HistoryRuntime,
        rolling_runtime: _RollingRuntime,
        application_root: Path,
    ) -> None:
        if not callable(getattr(history_runtime, 'scan_table', None)):
            raise TypeError('history_runtime must provide a callable scan_table method')
        if not callable(getattr(rolling_runtime, 'read_table', None)):
            raise TypeError('rolling_runtime must provide a callable read_table method')
        if not callable(getattr(rolling_runtime, 'replace', None)):
            raise TypeError('rolling_runtime must provide a callable replace method')
        if not isinstance(application_root, Path):
            raise TypeError('application_root must be Path')
        self._history_runtime = history_runtime
        self._rolling_runtime = rolling_runtime
        self._path = rolling_path(application_root)

    @property
    def path(self) -> Path:
        return self._path

    def is_coherent(self, authority: KpiHistorianAuthority) -> bool:
        if not isinstance(authority, KpiHistorianAuthority):
            raise TypeError('authority must be KpiHistorianAuthority')
        _require_grid_aligned(authority.watermark_utc)
        current, corrupted = self._read_optional()
        if corrupted or current is None:
            return False
        if current.metadata.watermark_utc > authority.watermark_utc:
            raise KpiHistorianRollingError(
                'KPI historian rolling watermark must not be ahead of historian authority'
            )
        return (
            current.metadata.watermark_utc == authority.watermark_utc
            and current.metadata.historian_revision == authority.revision
        )

    def materialize(
        self,
        *,
        batches: Iterable[KpiEvaluationBatch],
        previous_authority: KpiHistorianAuthority | None,
        authority: KpiHistorianAuthority,
        check_current: Callable[[], None] | None = None,
    ) -> None:
        if isinstance(batches, KpiEvaluationBatch | str | bytes):
            raise TypeError('batches must be an iterable of KpiEvaluationBatch values')
        if previous_authority is not None and not isinstance(
            previous_authority,
            KpiHistorianAuthority,
        ):
            raise TypeError('previous_authority must be KpiHistorianAuthority or None')
        if not isinstance(authority, KpiHistorianAuthority):
            raise TypeError('authority must be KpiHistorianAuthority')
        if check_current is not None and not callable(check_current):
            raise TypeError('check_current must be callable or None')
        _require_grid_aligned(authority.watermark_utc)
        batch_values = _batches(
            batches,
            through=KpiWatermark(authority.watermark_utc),
        )
        _check_current(check_current)

        current, corrupted = self._read_optional()
        rebuild_required = corrupted
        if current is not None:
            if current.metadata.watermark_utc > authority.watermark_utc:
                raise KpiHistorianRollingError(
                    'KPI historian rolling watermark must not exceed target authority'
                )
            if (
                previous_authority is not None
                and current.metadata.watermark_utc < previous_authority.watermark_utc
            ):
                rebuild_required = True
        elif previous_authority is not None:
            rebuild_required = True

        if rebuild_required:
            points, value_types = self._read_durable(
                authority=authority,
                check_current=check_current,
            )
        else:
            points = {} if current is None else _copy_points(current.points)
            value_types = {} if current is None else dict(current.value_types)
            _apply_batches(
                points=points,
                value_types=value_types,
                batches=batch_values,
            )
            _trim(
                points=points,
                value_types=value_types,
                watermark_utc=authority.watermark_utc,
            )

        _check_current(check_current)
        self._write(
            authority=authority,
            points=points,
            value_types=value_types,
        )

    def rebuild(
        self,
        *,
        authority: KpiHistorianAuthority,
        check_current: Callable[[], None] | None = None,
    ) -> None:
        if not isinstance(authority, KpiHistorianAuthority):
            raise TypeError('authority must be KpiHistorianAuthority')
        if check_current is not None and not callable(check_current):
            raise TypeError('check_current must be callable or None')
        _require_grid_aligned(authority.watermark_utc)
        _check_current(check_current)
        points, value_types = self._read_durable(
            authority=authority,
            check_current=check_current,
        )
        _check_current(check_current)
        self._write(
            authority=authority,
            points=points,
            value_types=value_types,
        )

    def _read_optional(self) -> tuple[_RollingState | None, bool]:
        try:
            return self._read_current(), False
        except DatasetRuntimeNotFoundError:
            return None, False
        except KpiHistorianRollingError:
            return None, True

    def _read_current(self) -> _RollingState:
        try:
            result = self._rolling_runtime.read_table(
                definition=rolling_definition(),
                target=rolling_target(),
            )
            metadata, points = rolling_state_from_table(result.table)
        except DatasetRuntimeNotFoundError:
            raise
        except (
            DatasetRuntimeReadError,
            DatasetRuntimeValidationError,
            KpiHistoryContractError,
        ) as error:
            raise KpiHistorianRollingError(
                'KPI historian rolling publication is invalid'
            ) from error
        return _RollingState(
            metadata=metadata,
            points=points,
            value_types=dict(metadata.value_types),
        )

    def _read_durable(
        self,
        *,
        authority: KpiHistorianAuthority,
        check_current: Callable[[], None] | None,
    ) -> tuple[dict[datetime, dict[str, str]], dict[str, str]]:
        end_utc = authority.watermark_utc
        start_utc = end_utc - timedelta(hours=ROLLING_MAX_HOURS)
        filters = (
            ColumnFilter(
                column='timestamp_utc',
                operator=FilterOperator.GREATER_THAN,
                value=start_utc,
            ),
            ColumnFilter(
                column='timestamp_utc',
                operator=FilterOperator.LESS_THAN_OR_EQUAL,
                value=end_utc,
            ),
        )
        records: list[dict[str, object]] = []
        for day in _days(start_utc.date(), end_utc.date()):
            _check_current(check_current)
            try:
                result = self._history_runtime.scan_table(
                    definition=history_definition(),
                    targets=(history_target(day),),
                    columns=(
                        'timestamp_utc',
                        'key',
                        'status',
                        'value_kind',
                        'value_type',
                        'value',
                    ),
                    filters=filters,
                )
            except DatasetRuntimeNotFoundError:
                continue
            records.extend(history_records_from_table(result.table))
        points: dict[datetime, dict[str, str]] = {}
        value_types: dict[str, str] = {}
        for row in sorted(records, key=_history_sort_key):
            _apply_history_row(
                points=points,
                value_types=value_types,
                row=row,
            )
        _trim(
            points=points,
            value_types=value_types,
            watermark_utc=end_utc,
        )
        return points, value_types

    def _write(
        self,
        *,
        authority: KpiHistorianAuthority,
        points: dict[datetime, dict[str, str]],
        value_types: dict[str, str],
    ) -> None:
        _prune(points=points, value_types=value_types)
        timestamps = sorted(points)
        metadata = KpiRollingMetadata(
            watermark_utc=authority.watermark_utc,
            historian_revision=authority.revision,
            coverage_start_utc=None if not timestamps else timestamps[0],
            coverage_end_utc=None if not timestamps else timestamps[-1],
            value_types=value_types,
        )
        try:
            self._rolling_runtime.replace(
                definition=rolling_definition(),
                target=rolling_target(),
                data=rolling_table(
                    metadata=metadata,
                    points=points,
                ),
            )
        except (
            DatasetRuntimeValidationError,
            DatasetRuntimeWriteError,
            KpiHistoryContractError,
        ) as error:
            raise KpiHistorianRollingError('KPI historian rolling publication failed') from error


def _batches(
    values: Iterable[KpiEvaluationBatch],
    *,
    through: KpiWatermark,
) -> tuple[KpiEvaluationBatch, ...]:
    try:
        resolved = tuple(values)
    except TypeError as error:
        raise TypeError('batches must be an iterable of KpiEvaluationBatch values') from error
    previous: KpiWatermark | None = None
    for batch in resolved:
        if not isinstance(batch, KpiEvaluationBatch):
            raise TypeError('batches must contain KpiEvaluationBatch values')
        _require_grid_aligned(batch.watermark.timestamp_utc)
        if previous is not None and batch.watermark <= previous:
            raise KpiHistorianRollingError('KPI rolling batches must be strictly ordered')
        if batch.watermark > through:
            raise KpiHistorianRollingError('KPI rolling batch exceeds target authority')
        previous = batch.watermark
    return resolved


def _apply_batches(
    *,
    points: dict[datetime, dict[str, str]],
    value_types: dict[str, str],
    batches: tuple[KpiEvaluationBatch, ...],
) -> None:
    for batch in batches:
        timestamp = batch.watermark.timestamp_utc
        for evaluation in batch.evaluations:
            if not evaluation.persist_history:
                continue
            row = points.get(timestamp)
            if row is not None:
                row.pop(evaluation.key, None)
            if evaluation.status is not KpiStatus.OK:
                continue
            if evaluation.value_kind is KpiValueKind.JSON:
                _clear_series(
                    points=points,
                    value_types=value_types,
                    key=evaluation.key,
                )
                continue
            value_type = None if evaluation.value_type is None else evaluation.value_type.value
            if value_type not in ROLLING_VALUE_TYPES or not isinstance(evaluation.value, str):
                raise KpiHistorianRollingError('KPI rolling scalar evaluation is invalid')
            _accept_type(
                points=points,
                value_types=value_types,
                key=evaluation.key,
                value_type=value_type,
            )
            points.setdefault(timestamp, {})[evaluation.key] = evaluation.value


def _apply_history_row(
    *,
    points: dict[datetime, dict[str, str]],
    value_types: dict[str, str],
    row: dict[str, object],
) -> None:
    timestamp = row.get('timestamp_utc')
    key = row.get('key')
    status = row.get('status')
    value_kind = row.get('value_kind')
    value_type = row.get('value_type')
    value = row.get('value')
    if not isinstance(timestamp, datetime):
        raise KpiHistorianRollingError('KPI durable history timestamp_utc is invalid')
    _require_grid_aligned(timestamp)
    if not isinstance(key, str) or not key:
        raise KpiHistorianRollingError('KPI durable history key is invalid')
    if status not in {'ok', 'missing', 'error'}:
        raise KpiHistorianRollingError('KPI durable history status is invalid')
    if value_kind not in {'value', 'json'}:
        raise KpiHistorianRollingError('KPI durable history value_kind is invalid')
    if status != 'ok':
        return
    if value_kind == 'json':
        _clear_series(
            points=points,
            value_types=value_types,
            key=key,
        )
        return
    if value_type not in ROLLING_VALUE_TYPES or not isinstance(value, str):
        raise KpiHistorianRollingError('KPI durable history scalar value is invalid')
    _accept_type(
        points=points,
        value_types=value_types,
        key=key,
        value_type=value_type,
    )
    points.setdefault(timestamp, {})[key] = value


def _accept_type(
    *,
    points: dict[datetime, dict[str, str]],
    value_types: dict[str, str],
    key: str,
    value_type: str,
) -> None:
    previous = value_types.get(key)
    if previous is not None and previous != value_type:
        _clear_series(
            points=points,
            value_types=value_types,
            key=key,
        )
    value_types[key] = value_type


def _clear_series(
    *,
    points: dict[datetime, dict[str, str]],
    value_types: dict[str, str],
    key: str,
) -> None:
    for row in points.values():
        row.pop(key, None)
    value_types.pop(key, None)


def _trim(
    *,
    points: dict[datetime, dict[str, str]],
    value_types: dict[str, str],
    watermark_utc: datetime,
) -> None:
    cutoff = watermark_utc - timedelta(hours=ROLLING_MAX_HOURS)
    for timestamp in tuple(points):
        if timestamp <= cutoff or timestamp > watermark_utc:
            del points[timestamp]
    _prune(points=points, value_types=value_types)


def _prune(
    *,
    points: dict[datetime, dict[str, str]],
    value_types: dict[str, str],
) -> None:
    for timestamp in tuple(points):
        if not points[timestamp]:
            del points[timestamp]
    used = {key for row in points.values() for key in row}
    for key in tuple(value_types):
        if key not in used:
            del value_types[key]


def _copy_points(
    points: dict[datetime, dict[str, str]],
) -> dict[datetime, dict[str, str]]:
    return {timestamp: dict(values) for timestamp, values in points.items()}


def _history_sort_key(
    row: dict[str, object],
) -> tuple[datetime, str]:
    timestamp = row.get('timestamp_utc')
    key = row.get('key')
    if not isinstance(timestamp, datetime) or not isinstance(key, str):
        raise KpiHistorianRollingError('KPI durable history row identity is invalid')
    return timestamp, key


def _days(start: date, end: date) -> tuple[date, ...]:
    if end < start:
        return ()
    count = (end - start).days
    return tuple(start + timedelta(days=index) for index in range(count + 1))


def _require_grid_aligned(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise KpiHistorianRollingError('KPI historian rolling timestamp must be timezone-aware')
    if value.microsecond != 0 or int(value.timestamp()) % ROLLING_GRID_SECONDS != 0:
        raise KpiHistorianRollingError(
            f'KPI historian rolling timestamp must align to the {ROLLING_GRID_SECONDS}-second grid'
        )


def _check_current(
    check_current: Callable[[], None] | None,
) -> None:
    if check_current is not None:
        check_current()
