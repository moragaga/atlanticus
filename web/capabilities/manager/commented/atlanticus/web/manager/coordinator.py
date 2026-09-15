# Coordinador de Manager con routing explícito por capability.
# Los módulos legacy conservan validación mediante workflow_service; un módulo exact-source
# debe declarar validator y reader explícitos y nunca cae silenciosamente al lifecycle legacy.
from datetime import UTC, datetime

from atlanticus.web.manager.authorization import ManagerAuthorizationPolicy
from atlanticus.web.manager.errors import (
    ManagerAuthorizationError,
    ManagerProjectionError,
    ManagerSourceConflictError,
)
from atlanticus.web.manager.exact_source import (
    ExactSourcePublicationResult,
    ExactSourcePublicationWorkflow,
    ExactSourceReaderWorkflow,
    ExactSourceReadResult,
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
from atlanticus.web.manager.validation import DraftValidationWorkflow
from atlanticus.web.projection.models import ProjectionTarget
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceSnapshot as ExactSourceSnapshot


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

    def get_current_projection_target(
        self,
        module_key: str,
        principal: ManagerPrincipal,
    ) -> ProjectionTarget | None:
        module, workflow = self._resolve(module_key)
        if not self._authorization.can_view(principal, module):
            raise ManagerAuthorizationError('Manager module access is denied')
        return workflow.get_current_projection_target()

    def validate_draft(
        self,
        module_key: str,
        principal: ManagerPrincipal,
        payload: dict[str, object],
    ) -> DraftValidationResult:
        module, workflow = self._resolve_validation(module_key)
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

    def get_exact_source_snapshot(
        self,
        module_key: str,
        principal: ManagerPrincipal,
    ) -> ExactSourceSnapshot:
        module, workflow = self._resolve_exact_source(module_key)
        if not self._authorization.can_view(principal, module):
            raise ManagerAuthorizationError('Manager module access is denied')
        return workflow.get_source_snapshot()

    def load_current_source_exact(
        self,
        module_key: str,
        principal: ManagerPrincipal,
    ) -> ExactSourceReadResult:
        module, workflow = self._resolve_exact_source_reader(module_key)
        if not self._authorization.can_view(principal, module):
            raise ManagerAuthorizationError('Manager module access is denied')
        return workflow.load_current_source_exact()

    def publish_draft_exact(
        self,
        module_key: str,
        principal: ManagerPrincipal,
        payload: dict[str, object],
        expected_source_snapshot: ExactSourceSnapshot,
    ) -> ExactSourcePublicationResult:
        module, workflow = self._resolve_exact_source(module_key)
        if not self._authorization.can_publish(principal, module):
            raise ManagerAuthorizationError('Manager source publication access is denied')
        current = workflow.get_source_snapshot()
        if current != expected_source_snapshot:
            raise ManagerSourceConflictError(
                'Manager source changed while the draft was being edited'
            )
        try:
            return workflow.publish_draft_exact(payload, expected_source_snapshot)
        except Exception as error:
            refreshed = workflow.get_source_snapshot()
            if refreshed != expected_source_snapshot:
                raise ManagerSourceConflictError(
                    'Manager source changed before publication completed'
                ) from error
            raise

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
        target: ProjectionTarget,
    ) -> ProjectionExecutionResult:
        module, workflow = self._resolve(module_key)
        if not self._authorization.can_project(principal, module):
            raise ManagerAuthorizationError('Manager projection access is denied')
        return workflow.project(target)

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

    def _resolve(
        self,
        module_key: str,
    ) -> tuple[ManagerModule, ConfigurationLifecycleWorkflow]:
        module = self._registry.require(module_key)
        # Un módulo exact-only no cae implícitamente al lifecycle legacy.
        service_key = module.workflow_service
        if service_key is None:
            raise ManagerProjectionError(
                'Manager module does not declare a legacy lifecycle workflow service'
            )
        workflow = self._services.require(service_key)
        if not isinstance(workflow, ConfigurationLifecycleWorkflow):
            raise ManagerProjectionError('Manager lifecycle workflow has an invalid contract')
        return module, workflow

    def _resolve_validation(
        self,
        module_key: str,
    ) -> tuple[ManagerModule, DraftValidationWorkflow]:
        module = self._registry.require(module_key)
        service_key = module.draft_validation_service
        if service_key is None:
            if (
                module.exact_source_workflow_service is not None
                or module.exact_source_reader_service is not None
            ):
                raise ManagerProjectionError(
                    'Manager exact-source module does not declare a draft validation service'
                )
            service_key = module.workflow_service
        workflow = self._services.require(service_key)
        if not isinstance(workflow, DraftValidationWorkflow):
            raise ManagerProjectionError('Manager draft validation workflow has an invalid contract')
        return module, workflow

    def _resolve_exact_source(
        self,
        module_key: str,
    ) -> tuple[ManagerModule, ExactSourcePublicationWorkflow]:
        module = self._registry.require(module_key)
        service_key = module.exact_source_workflow_service
        if service_key is None:
            raise ManagerProjectionError(
                'Manager module does not declare an exact source workflow service'
            )
        workflow = self._services.require(service_key)
        if not isinstance(workflow, ExactSourcePublicationWorkflow):
            raise ManagerProjectionError(
                'Manager exact source workflow has an invalid contract'
            )
        return module, workflow

    def _resolve_exact_source_reader(
        self,
        module_key: str,
    ) -> tuple[ManagerModule, ExactSourceReaderWorkflow]:
        module = self._registry.require(module_key)
        service_key = module.exact_source_reader_service
        if service_key is None:
            raise ManagerProjectionError(
                'Manager module does not declare an exact source reader service'
            )
        workflow = self._services.require(service_key)
        if not isinstance(workflow, ExactSourceReaderWorkflow):
            raise ManagerProjectionError(
                'Manager exact source reader has an invalid contract'
            )
        return module, workflow
