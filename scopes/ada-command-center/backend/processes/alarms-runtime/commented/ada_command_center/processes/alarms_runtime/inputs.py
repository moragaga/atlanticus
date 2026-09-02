# Espejo comentado: Contratos de valores operacionales ya adquiridos; no define transporte físico.
# Mantiene exactamente los mismos tokens ejecutables que el archivo productivo.

from __future__ import annotations

from dataclasses import dataclass

from ada_command_center.alarms.core import DeactivationDecision, DeactivationRequest, ManagementAction


@dataclass(frozen=True, slots=True)
class AlarmPendingDeactivationRequest:
    request: DeactivationRequest
    priority_group: str

    def __post_init__(self) -> None:
        if not isinstance(self.request, DeactivationRequest):
            raise TypeError('request must be DeactivationRequest')
        if not isinstance(self.priority_group, str) or not self.priority_group.strip():
            raise ValueError('priority_group must be a non-empty string')
        object.__setattr__(self, 'priority_group', self.priority_group.strip())

    @property
    def request_id(self) -> str:
        return self.request.request_id


@dataclass(frozen=True, slots=True)
class AlarmOperationalInputs:
    management_actions: tuple[ManagementAction, ...] = ()
    pending_deactivation_requests: tuple[AlarmPendingDeactivationRequest, ...] = ()
    deactivation_decisions: tuple[DeactivationDecision, ...] = ()

    def __post_init__(self) -> None:
        _require_typed_tuple(self.management_actions, ManagementAction, 'management_actions')
        _require_typed_tuple(
            self.pending_deactivation_requests,
            AlarmPendingDeactivationRequest,
            'pending_deactivation_requests',
        )
        _require_typed_tuple(
            self.deactivation_decisions,
            DeactivationDecision,
            'deactivation_decisions',
        )
        _require_unique(self.management_actions, 'input_id', 'management_actions')
        _require_unique(
            self.pending_deactivation_requests,
            'request_id',
            'pending_deactivation_requests',
        )
        _require_unique(self.deactivation_decisions, 'decision_id', 'deactivation_decisions')
        request_ids = {pending.request.request_id for pending in self.pending_deactivation_requests}
        for decision in self.deactivation_decisions:
            if decision.request_id not in request_ids:
                raise ValueError('deactivation decision must reference a pending durable request')


def _require_typed_tuple(value: object, expected: type, name: str) -> None:
    if not isinstance(value, tuple) or not all(isinstance(item, expected) for item in value):
        raise TypeError(f'{name} must contain {expected.__name__} values')


def _require_unique(values: tuple[object, ...], attribute: str, name: str) -> None:
    identifiers = [getattr(value, attribute) for value in values]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError(f'{name} must not contain duplicate {attribute}')
