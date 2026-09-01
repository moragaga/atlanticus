from datetime import UTC, datetime

from atlanticus.web.manager.authorization import ManagerAuthorizationPolicy
from atlanticus.web.manager.errors import (
    ManagerAuthorizationError,
    ManagerProjectionError,
    ManagerSourceConflictError,
)
from atlanticus.web.manager.models import ManagerModule, ManagerPrincipal
from atlanticus.web.manager.projection import (
    ConfigurationLifecycleWorkflow,
    DraftValidationResult,
    ProjectionExecutionResult,
    ProjectionStatus,
    RevisionHistoryEntry,
    RevisionHistoryWorkflow,
    SourcePublicationResult,
    SourceSnapshot,
    SourceVerificationResult,
)
from atlanticus.web.manager.registry import ManagerModuleRegistry
from atlanticus.web.services import ServiceRegistry


class ManagerProjectionCoordinator:
    def __init__(
        self,
        *,
        registry: ManagerModuleRegistry,
        services: ServiceRegistry,
        authorization: ManagerAuthorizationPolicy,
    ) -> None:
        self._registry = registry
        self._services = services
        self._authorization = authorization

    def get_status(self, module_key: str, principal: ManagerPrincipal) -> ProjectionStatus:
        module, workflow = self._resolve(module_key)
        if not self._authorization.can_view(principal, module):
            raise ManagerAuthorizationError('Manager module access is denied')
        return workflow.get_status()

    def validate_draft(
        self,
        module_key: str,
        principal: ManagerPrincipal,
        payload: dict[str, object],
    ) -> DraftValidationResult:
        module, workflow = self._resolve(module_key)
        if not self._authorization.can_validate(principal, module):
            raise ManagerAuthorizationError('Manager validation access is denied')
        return workflow.validate_draft(payload)

    def verify_source(
        self,
        module_key: str,
        principal: ManagerPrincipal,
        *,
        draft_revision: str,
        base_source_revision: str | None,
    ) -> SourceVerificationResult:
        module, workflow = self._resolve(module_key)
        if not self._authorization.can_publish(principal, module):
            raise ManagerAuthorizationError('Manager source verification access is denied')
        revision = draft_revision.strip()
        if not revision:
            raise ManagerProjectionError('Draft revision must not be empty')
        status = workflow.get_status()
        return SourceVerificationResult(
            draft_revision=revision,
            base_source_revision=base_source_revision,
            source_revision=status.source_revision,
            source_audit=status.source_audit,
            checked_at=datetime.now(UTC),
        )

    def publish_draft(
        self,
        module_key: str,
        principal: ManagerPrincipal,
        payload: dict[str, object],
        expected_source_revision: str | None,
    ) -> SourcePublicationResult:
        module, workflow = self._resolve(module_key)
        if not self._authorization.can_publish(principal, module):
            raise ManagerAuthorizationError('Manager source publication access is denied')
        return self._publish(
            workflow,
            payload=payload,
            expected_source_revision=expected_source_revision,
        )

    def force_publish_draft(
        self,
        module_key: str,
        principal: ManagerPrincipal,
        payload: dict[str, object],
        *,
        base_source_revision: str | None,
        expected_source_revision: str,
    ) -> SourcePublicationResult:
        module, workflow = self._resolve(module_key)
        if not module.force_publish_enabled:
            raise ManagerAuthorizationError('Manager force publication is not enabled')
        if not self._authorization.can_publish(principal, module):
            raise ManagerAuthorizationError('Manager source publication access is denied')
        current = self._require_expected_source(workflow, expected_source_revision)
        if base_source_revision == current.source_revision:
            raise ManagerProjectionError('Manager force publication requires a source conflict')
        return self._publish(
            workflow,
            payload=payload,
            expected_source_revision=expected_source_revision,
        )

    def load_current_source(
        self,
        module_key: str,
        principal: ManagerPrincipal,
    ) -> SourceSnapshot:
        module, workflow = self._resolve(module_key)
        if not self._authorization.can_view(principal, module):
            raise ManagerAuthorizationError('Manager module access is denied')
        if not isinstance(workflow, RevisionHistoryWorkflow):
            raise ManagerProjectionError('Manager workflow does not support source loading')
        status = workflow.get_status()
        if status.source_revision is None or status.source_audit is None:
            raise ManagerProjectionError('Manager source does not exist')
        payload = workflow.load_revision(status.source_revision)
        refreshed = workflow.get_status()
        if refreshed.source_revision != status.source_revision:
            raise ManagerSourceConflictError('Manager source changed while it was being loaded')
        return SourceSnapshot(
            revision=status.source_revision,
            audit=status.source_audit,
            payload=payload,
        )

    def project(
        self,
        module_key: str,
        principal: ManagerPrincipal,
        expected_source_revision: str,
    ) -> ProjectionExecutionResult:
        module, workflow = self._resolve(module_key)
        if not self._authorization.can_project(principal, module):
            raise ManagerAuthorizationError('Manager projection access is denied')
        revision = expected_source_revision.strip()
        if not revision:
            raise ManagerProjectionError('Expected source revision must not be empty')
        return workflow.project(revision)

    def can_load_history(self, module_key: str, principal: ManagerPrincipal) -> bool:
        module, workflow = self._resolve(module_key)
        return isinstance(workflow, RevisionHistoryWorkflow) and self._authorization.can_view(
            principal, module
        )

    def load_history_revision(
        self,
        module_key: str,
        principal: ManagerPrincipal,
        revision: str,
    ) -> dict[str, object]:
        module, workflow = self._resolve(module_key)
        if not isinstance(workflow, RevisionHistoryWorkflow):
            raise ManagerProjectionError('Manager workflow does not support history loading')
        if not self._authorization.can_view(principal, module):
            raise ManagerAuthorizationError('Manager module access is denied')
        normalized = revision.strip()
        if not normalized:
            raise ManagerProjectionError('History revision must not be empty')
        return workflow.load_revision(normalized)

    def list_history(
        self,
        module_key: str,
        principal: ManagerPrincipal,
        *,
        limit: int = 20,
    ) -> tuple[RevisionHistoryEntry, ...]:
        module, workflow = self._resolve(module_key)
        if not self._authorization.can_view(principal, module):
            raise ManagerAuthorizationError('Manager module access is denied')
        if not isinstance(workflow, RevisionHistoryWorkflow):
            return ()
        return workflow.list_history(limit=limit)

    def _publish(
        self,
        workflow: ConfigurationLifecycleWorkflow,
        *,
        payload: dict[str, object],
        expected_source_revision: str | None,
    ) -> SourcePublicationResult:
        self._require_expected_source(workflow, expected_source_revision)
        try:
            return workflow.publish_draft(payload, expected_source_revision)
        except Exception as error:
            refreshed = workflow.get_status()
            if refreshed.source_revision != expected_source_revision:
                raise ManagerSourceConflictError(
                    'Manager source changed before publication completed'
                ) from error
            raise

    def _require_expected_source(
        self,
        workflow: ConfigurationLifecycleWorkflow,
        expected_source_revision: str | None,
    ) -> ProjectionStatus:
        status = workflow.get_status()
        if status.source_revision != expected_source_revision:
            raise ManagerSourceConflictError(
                'Manager source changed while the draft was being edited'
            )
        return status

    def _resolve(self, module_key: str) -> tuple[ManagerModule, ConfigurationLifecycleWorkflow]:
        module = self._registry.require(module_key)
        workflow = self._services.require(module.workflow_service)
        if not isinstance(workflow, ConfigurationLifecycleWorkflow):
            raise ManagerProjectionError('Manager lifecycle workflow has an invalid contract')
        return module, workflow
