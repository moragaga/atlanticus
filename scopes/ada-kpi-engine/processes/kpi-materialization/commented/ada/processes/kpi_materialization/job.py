# Espejo pedagógico de readiness de KPI Materialization: job.py.
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ada.kpis.materialization import (
    KpiMaterializationContractError,
    KpiMaterializationStoreError,
    LocalKpiRegistryStore,
    materialize_registry,
    require_tool_key,
)
from ada.processes.kpi_materialization.errors import (
    KpiMaterializationAcquisitionError,
    KpiMaterializationIterationError,
    KpiMaterializationRegistryPending,
)
from ada.processes.kpi_materialization.repository import KpiRegistryReader
from atlanticus.runtime import JobRuntimeContext

READINESS_RETRY_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
# Define una responsabilidad con estado o contrato propio.
class KpiMaterializationIterationResult:
    configured_tools: int
    updated_tools: int
    unchanged_tools: int
    removed_tools: int
    pending_tools: int


# Define una responsabilidad con estado o contrato propio.
class KpiMaterializationJob:
    def __init__(
        self,
        *,
        repositories: Mapping[str, KpiRegistryReader],
        store: LocalKpiRegistryStore,
    ) -> None:
        if not isinstance(repositories, Mapping) or not repositories:
            raise ValueError('repositories must contain at least one tool')
        self._repositories = {
            require_tool_key(tool_key): reader
            for tool_key, reader in sorted(repositories.items())
        }
        self._store = store

    def run_iteration(
        self,
        context: JobRuntimeContext,
    ) -> KpiMaterializationIterationResult:
        updated = 0
        unchanged = 0
        pending = 0
        failures: list[tuple[str, Exception]] = []

        for tool_key, repository in self._repositories.items():
            context.raise_if_cancelled()
            try:
                projection = repository.read()
                materialized = materialize_registry(
                    tool_key=tool_key,
                    projection=projection,
                )
                current = self._store.read(tool_key)
                if current == materialized:
                    unchanged += 1
                    continue
                context.raise_if_cancelled()
                context.assert_lease_current()
                with context.fenced_mutation():
                    self._store.replace(
                        tool_key=tool_key,
                        document=materialized,
                    )
                context.mark_iteration_work()
                updated += 1
            except KpiMaterializationRegistryPending:
                pending += 1
            except (
                KpiMaterializationAcquisitionError,
                KpiMaterializationContractError,
                KpiMaterializationStoreError,
            ) as error:
                failures.append((tool_key, error))

        context.raise_if_cancelled()
        context.assert_lease_current()
        with context.fenced_mutation():
            removed = self._store.remove_unconfigured(self._repositories)
        if removed:
            context.mark_iteration_work()

        result = KpiMaterializationIterationResult(
            configured_tools=len(self._repositories),
            updated_tools=updated,
            unchanged_tools=unchanged,
            removed_tools=len(removed),
            pending_tools=pending,
        )
        self._record(context, result, failures)

        if failures:
            failed_tools = ', '.join(tool_key for tool_key, _ in failures)
            raise KpiMaterializationIterationError(
                f'KPI materialization failed for tools: {failed_tools}'
            ) from failures[0][1]
        if pending:
            context.set_next_iteration_delay(READINESS_RETRY_SECONDS)
        return result

    @staticmethod
    def _record(
        context: JobRuntimeContext,
        result: KpiMaterializationIterationResult,
        failures: list[tuple[str, Exception]],
    ) -> None:
        context.set_iteration_fact('configured_tools', result.configured_tools)
        context.set_iteration_fact('updated_tools', result.updated_tools)
        context.set_iteration_fact('unchanged_tools', result.unchanged_tools)
        context.set_iteration_fact('removed_tools', result.removed_tools)
        context.set_iteration_fact('pending_tools', result.pending_tools)
        context.set_iteration_fact('failed_tools', len(failures))
