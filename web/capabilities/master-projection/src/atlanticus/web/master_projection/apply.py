from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from atlanticus.web.master_projection.plan import (
    MasterProjectionPlanner,
    ProjectionDomain,
    ProjectionPlanState,
)
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.source.models import SourceKey


class MasterApplyOutcome(StrEnum):
    APPLIED = 'APPLIED'
    ALREADY_CURRENT = 'ALREADY_CURRENT'


class MasterApplyError(Exception):
    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class MasterApplyResult:
    source_key: SourceKey
    target: ProjectionTarget
    outcome: MasterApplyOutcome


class MasterProjectionExecutor:
    def __init__(
        self,
        *,
        planner: MasterProjectionPlanner,
        domains: tuple[ProjectionDomain, ...],
    ) -> None:
        registered = {domain.key: domain for domain in domains}
        if len(registered) != len(domains) or not registered:
            raise ValueError('Master Projection domains must be unique and non-empty')
        self._planner = planner
        self._domains = registered

    def apply(
        self,
        *,
        source_key: SourceKey,
        expected_target: ProjectionTarget,
    ) -> MasterApplyResult:
        if not isinstance(source_key, SourceKey) or not isinstance(
            expected_target, ProjectionTarget
        ):
            raise MasterApplyError('Invalid projection selection', reason='INVALID_SELECTION')
        domain = self._domains.get(source_key)
        if domain is None or expected_target.source_key != source_key:
            raise MasterApplyError('Projection domain is not supported', reason='INVALID_SELECTION')

        plan = self._planner.inspect()
        entry = next((item for item in plan.entries if item.key == source_key), None)
        if entry is None:
            raise MasterApplyError('Projection domain is not available', reason='UNAVAILABLE')
        if entry.state not in (
            ProjectionPlanState.CURRENT,
            ProjectionPlanState.NEVER_PROJECTED,
            ProjectionPlanState.OUTDATED,
        ):
            raise MasterApplyError('Projection is not ready', reason=entry.state.value)
        if entry.current_target != expected_target:
            raise MasterApplyError('Projection selection is outdated', reason='STALE_SELECTION')
        if entry.state is ProjectionPlanState.CURRENT:
            return MasterApplyResult(
                source_key, expected_target, MasterApplyOutcome.ALREADY_CURRENT
            )

        try:
            current_target = domain.service.select_current_target(source_key)
            active = domain.projection.get_active(source_key)
        except Exception as error:
            raise MasterApplyError(
                'Projection state is unavailable', reason='UNAVAILABLE'
            ) from error
        if current_target != expected_target:
            raise MasterApplyError('Projection selection is outdated', reason='STALE_SELECTION')
        if active is not None and active.target == expected_target:
            return MasterApplyResult(
                source_key, expected_target, MasterApplyOutcome.ALREADY_CURRENT
            )

        try:
            executed = domain.service.project(expected_target)
        except Exception as error:
            raise MasterApplyError(
                'Projection execution failed', reason='EXECUTION_FAILED'
            ) from error
        if executed.target != expected_target or executed.projection.target != expected_target:
            raise MasterApplyError(
                'Projection result does not match selection', reason='VERIFICATION_FAILED'
            )
        try:
            persisted = domain.projection.get_active(source_key)
            current = domain.service.select_current_target(source_key)
        except Exception as error:
            raise MasterApplyError(
                'Projection result could not be verified', reason='VERIFICATION_FAILED'
            ) from error
        if persisted is None or persisted.target != expected_target or current != expected_target:
            raise MasterApplyError(
                'Projection result could not be verified', reason='VERIFICATION_FAILED'
            )
        return MasterApplyResult(source_key, expected_target, MasterApplyOutcome.APPLIED)
