# Adapta contratos de dominio al Manager sin incorporar reglas de negocio.
from __future__ import annotations

from ada.configuration.tools import ToolConfiguration
from ada.configuration.tools_lifecycle import ToolLifecycleServices
from atlanticus.web.manager import (
    DraftValidationResult,
    ProjectionAuditRecord,
    ProjectionExecutionResult,
    ProjectionIssue,
    ProjectionStatus,
    ProjectionSummaryItem,
    RevisionHistoryEntry,
    SourcePublicationResult,
)
from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationConfigurationServices,
)
from atlanticus.web.users.configuration import (
    UsersConfigurationCatalog,
    UsersConfigurationServices,
)


class ToolConfigurationManagerWorkflowAdapter:
    def __init__(self, services: ToolLifecycleServices) -> None:
        self._workflow = services.projection_workflow
        self._administration = services.administration

    def get_status(self) -> ProjectionStatus:
        return _status(self._workflow.get_status())

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        configuration = ToolConfiguration.from_document(payload)
        return _validation(self._administration.validate_configuration(configuration))

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_revision: str | None,
    ) -> SourcePublicationResult:
        configuration = ToolConfiguration.from_document(payload)
        return _publication(
            self._administration.publish_configuration(
                configuration,
                expected_source_revision=expected_source_revision,
            )
        )

    def project(self, expected_source_revision: str) -> ProjectionExecutionResult:
        return _projection(self._workflow.project(expected_source_revision))

    def load_revision(self, revision: str) -> dict[str, object]:
        return self._administration.load_revision_configuration(revision).to_document()

    def list_history(self, *, limit: int = 20) -> tuple[RevisionHistoryEntry, ...]:
        status = self._workflow.get_status()
        return tuple(
            _history_entry(
                document,
                active_source_revision=status.active_source_revision,
                source_revision=status.source_revision,
            )
            for document in self._administration.list_history(limit=limit)
        )


class NavigationManagerWorkflowAdapter:
    def __init__(self, services: NavigationConfigurationServices) -> None:
        self._workflow = services.projection_workflow
        self._administration = services.administration

    def get_status(self) -> ProjectionStatus:
        return _status(self._workflow.get_status())

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        catalog = NavigationConfigurationCatalog.from_document(payload)
        return _validation(self._administration.validate_catalog(catalog))

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_revision: str | None,
    ) -> SourcePublicationResult:
        catalog = NavigationConfigurationCatalog.from_document(payload)
        return _publication(
            self._administration.publish_catalog(
                catalog,
                expected_source_revision=expected_source_revision,
            )
        )

    def project(self, expected_source_revision: str) -> ProjectionExecutionResult:
        return _projection(self._workflow.project(expected_source_revision))

    def load_revision(self, revision: str) -> dict[str, object]:
        return self._administration.load_revision_catalog(revision).to_document()

    def list_history(self, *, limit: int = 20) -> tuple[RevisionHistoryEntry, ...]:
        status = self._workflow.get_status()
        return tuple(
            _history_entry(
                bundle,
                active_source_revision=status.active_source_revision,
                source_revision=status.source_revision,
            )
            for bundle in self._administration.list_history(limit=limit)
        )


class UsersManagerWorkflowAdapter:
    def __init__(self, services: UsersConfigurationServices) -> None:
        self._workflow = services.projection_workflow
        self._administration = services.administration

    def get_status(self) -> ProjectionStatus:
        return _status(self._workflow.get_status())

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        catalog = UsersConfigurationCatalog.from_document(payload)
        return _validation(self._administration.validate_catalog(catalog))

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_revision: str | None,
    ) -> SourcePublicationResult:
        catalog = UsersConfigurationCatalog.from_document(payload)
        return _publication(
            self._administration.publish_catalog(
                catalog,
                expected_source_revision=expected_source_revision,
            )
        )

    def project(self, expected_source_revision: str) -> ProjectionExecutionResult:
        return _projection(self._workflow.project(expected_source_revision))

    def load_revision(self, revision: str) -> dict[str, object]:
        return self._administration.load_revision_catalog(revision).to_document()

    def list_history(self, *, limit: int = 20) -> tuple[RevisionHistoryEntry, ...]:
        status = self._workflow.get_status()
        return tuple(
            _history_entry(
                bundle,
                active_source_revision=status.active_source_revision,
                source_revision=status.source_revision,
            )
            for bundle in self._administration.list_history(limit=limit)
        )


def _status(status) -> ProjectionStatus:
    return ProjectionStatus(
        source_revision=status.source_revision,
        source_audit=_optional_audit(status.source_audit),
        active_revision=status.active_revision,
        active_source_revision=status.active_source_revision,
        projection_audit=_optional_audit(status.projection_audit),
    )


def _validation(result) -> DraftValidationResult:
    return DraftValidationResult(
        draft_revision=result.draft_revision,
        valid=result.valid,
        audit=_audit(result.audit),
        issues=tuple(_issue(issue) for issue in result.issues),
        summary=tuple(_summary(item) for item in result.summary),
    )


def _publication(result) -> SourcePublicationResult:
    return SourcePublicationResult(
        source_revision=result.source_revision,
        published=result.published,
        audit=_audit(result.audit),
        summary=tuple(_summary(item) for item in result.summary),
    )


def _projection(result) -> ProjectionExecutionResult:
    return ProjectionExecutionResult(
        source_revision=result.source_revision,
        projection_revision=result.projection_revision,
        projected=result.projected,
        audit=_audit(result.audit),
        issues=tuple(_issue(issue) for issue in result.issues),
        summary=tuple(_summary(item) for item in result.summary),
    )


def _optional_audit(record) -> ProjectionAuditRecord | None:
    return _audit(record) if record is not None else None


def _audit(record) -> ProjectionAuditRecord:
    return ProjectionAuditRecord(
        actor=record.actor,
        occurred_at=record.occurred_at_utc,
    )


def _issue(issue) -> ProjectionIssue:
    return ProjectionIssue(
        code=issue.code,
        message=issue.message,
        level=issue.level,
        path=issue.path,
    )


def _summary(item) -> ProjectionSummaryItem:
    return ProjectionSummaryItem(
        label=item.label,
        value=item.value,
    )


def _history_entry(
    document,
    *,
    active_source_revision: str | None,
    source_revision: str | None,
) -> RevisionHistoryEntry:
    return RevisionHistoryEntry(
        revision=document.revision,
        saved_by=document.saved_by,
        saved_at=document.saved_at_utc,
        active=document.revision == active_source_revision,
        current=document.revision == source_revision,
    )
