# Espejo pedagógico del archivo productivo equivalente.
# Coordina los workflows de Manager después de una única autorización funcional del módulo; no autoriza por separado validar, publicar o proyectar.
# Los comentarios no alteran la estructura ejecutable ni el comportamiento del archivo productivo.

from atlanticus.web.manager.authorization import ManagerAuthorizationPolicy
from atlanticus.web.manager.errors import (
    ManagerAuthorizationError,
    ManagerProjectionError,
    ManagerSourceConflictError,
)
from atlanticus.web.manager.models import ManagerModule, ManagerPrincipal
from atlanticus.web.manager.projection import DraftValidationResult
from atlanticus.web.manager.registry import ManagerModuleRegistry
from atlanticus.web.manager.source import (
    SourceHistoryReadResult,
    SourceHistoryWorkflow,
    SourcePublicationResult,
    SourcePublicationWorkflow,
    SourceReaderWorkflow,
    SourceReadResult,
)
from atlanticus.web.manager.validation import DraftValidationWorkflow
from atlanticus.web.projection.models import (
    ProjectionExecutionResult,
    ProjectionStatus,
    ProjectionTarget,
)
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import HistoryPage, SourceReleaseRef, SourceSnapshot


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
        module, service = self._resolve_projection(module_key)
        self._require_module_access(principal, module)
        return service.get_status(module.source_key)

    def get_current_projection_target(
        self,
        module_key: str,
        principal: ManagerPrincipal,
    ) -> ProjectionTarget | None:
        module, service = self._resolve_projection(module_key)
        self._require_module_access(principal, module)
        return service.select_current_target(module.source_key)

    def validate_draft(
        self,
        module_key: str,
        principal: ManagerPrincipal,
        payload: dict[str, object],
    ) -> DraftValidationResult:
        module, workflow = self._resolve_validation(module_key)
        self._require_module_access(principal, module)
        return workflow.validate_draft(payload)

    def get_source_snapshot(
        self,
        module_key: str,
        principal: ManagerPrincipal,
    ) -> SourceSnapshot:
        module, workflow = self._resolve_source_publication(module_key)
        self._require_module_access(principal, module)
        snapshot = workflow.get_source_snapshot()
        self._validate_source_key(module, snapshot)
        return snapshot

    def load_current_source(
        self,
        module_key: str,
        principal: ManagerPrincipal,
    ) -> SourceReadResult:
        module, workflow = self._resolve_source_reader(module_key)
        self._require_module_access(principal, module)
        result = workflow.load_current_source()
        self._validate_source_key(module, result.snapshot)
        return result

    def publish_draft(
        self,
        module_key: str,
        principal: ManagerPrincipal,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> SourcePublicationResult:
        module, workflow = self._resolve_source_publication(module_key)
        self._require_module_access(principal, module)
        self._validate_source_key(module, expected_source_snapshot)
        current = workflow.get_source_snapshot()
        self._validate_source_key(module, current)
        if current.current != expected_source_snapshot.current:
            raise ManagerSourceConflictError(
                'Manager source changed while the draft was being edited'
            )
        try:
            result = workflow.publish_draft(payload, current)
        except Exception as error:
            refreshed = workflow.get_source_snapshot()
            self._validate_source_key(module, refreshed)
            if refreshed.current != expected_source_snapshot.current:
                raise ManagerSourceConflictError(
                    'Manager source changed before publication completed'
                ) from error
            raise
        self._validate_source_key(module, result.source.snapshot)
        return result

    def project(
        self,
        module_key: str,
        principal: ManagerPrincipal,
        target: ProjectionTarget,
    ) -> ProjectionExecutionResult[object]:
        module, service = self._resolve_projection(module_key)
        self._require_module_access(principal, module)
        if target.source_key != module.source_key:
            raise ManagerProjectionError('Projection target belongs to another source')
        return service.project(target)

    def can_load_history(self, module_key: str, principal: ManagerPrincipal) -> bool:
        module = self._registry.require(module_key)
        return bool(
            module.source_history_service is not None
            and self._authorization.can_view(principal, module)
        )

    def load_history_release(
        self,
        module_key: str,
        principal: ManagerPrincipal,
        release_ref: SourceReleaseRef,
    ) -> SourceHistoryReadResult:
        module, workflow = self._resolve_source_history(module_key)
        self._require_module_access(principal, module)
        result = workflow.load_history_release(release_ref)
        if result.release_ref != release_ref:
            raise ManagerProjectionError('Manager history returned a different source release')
        return result

    def list_history(
        self,
        module_key: str,
        principal: ManagerPrincipal,
        *,
        limit: int = 20,
    ) -> HistoryPage:
        module, workflow = self._resolve_source_history(module_key)
        self._require_module_access(principal, module)
        return workflow.list_history(limit=limit)

    def _resolve_validation(
        self,
        module_key: str,
    ) -> tuple[ManagerModule, DraftValidationWorkflow]:
        module = self._registry.require(module_key)
        workflow = self._services.require(module.draft_validation_service)
        if not isinstance(workflow, DraftValidationWorkflow):
            raise ManagerProjectionError(
                'Manager draft validation workflow has an invalid contract'
            )
        return module, workflow

    def _resolve_source_reader(
        self,
        module_key: str,
    ) -> tuple[ManagerModule, SourceReaderWorkflow]:
        module = self._registry.require(module_key)
        workflow = self._services.require(module.source_reader_service)
        if not isinstance(workflow, SourceReaderWorkflow):
            raise ManagerProjectionError('Manager source reader has an invalid contract')
        return module, workflow

    def _resolve_source_publication(
        self,
        module_key: str,
    ) -> tuple[ManagerModule, SourcePublicationWorkflow]:
        module = self._registry.require(module_key)
        workflow = self._services.require(module.source_service)
        if not isinstance(workflow, SourcePublicationWorkflow):
            raise ManagerProjectionError('Manager source workflow has an invalid contract')
        return module, workflow

    def _resolve_source_history(
        self,
        module_key: str,
    ) -> tuple[ManagerModule, SourceHistoryWorkflow]:
        module = self._registry.require(module_key)
        service_key = module.source_history_service
        if service_key is None:
            raise ManagerProjectionError('Manager module does not declare a source history service')
        workflow = self._services.require(service_key)
        if not isinstance(workflow, SourceHistoryWorkflow):
            raise ManagerProjectionError('Manager source history workflow has an invalid contract')
        return module, workflow

    def _resolve_projection(self, module_key: str) -> tuple[ManagerModule, object]:
        module = self._registry.require(module_key)
        service = self._services.require(module.projection_service)
        required = ('get_status', 'select_current_target', 'project')
        if any(not callable(getattr(service, name, None)) for name in required):
            raise ManagerProjectionError('Manager projection service has an invalid contract')
        return module, service

    def _require_module_access(
        self,
        principal: ManagerPrincipal,
        module: ManagerModule,
    ) -> None:
        if not self._authorization.can_view(principal, module):
            raise ManagerAuthorizationError('Manager module access is denied')

    @staticmethod
    def _validate_source_key(module: ManagerModule, snapshot: SourceSnapshot) -> None:
        if snapshot.source_key != module.source_key:
            raise ManagerProjectionError('Manager source service returned a different source key')
