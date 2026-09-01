# Expone el contrato público del renderer opcional de vista previa histórica por módulo.
# El contrato permite extender Manager sin acoplarlo a la semántica de Tools, Users o Navigation.

from atlanticus.web.manager.authorization import (
    DefaultManagerAuthorizationPolicy,
    ManagerAuthorizationPolicy,
)
from atlanticus.web.manager.coordinator import ManagerProjectionCoordinator
from atlanticus.web.manager.errors import (
    ManagerAuthorizationError,
    ManagerDefinitionError,
    ManagerError,
    ManagerProjectionError,
    ManagerSourceConflictError,
)
from atlanticus.web.manager.lifecycle import ManagerLifecycleState, resolve_manager_lifecycle
from atlanticus.web.manager.models import (
    ManagerApplicationDefinition,
    ManagerBrand,
    ManagerBrandMark,
    ManagerHistoryPreviewRenderer,
    ManagerModule,
    ManagerModuleAccess,
    ManagerModuleGroup,
    ManagerPrincipal,
    ManagerPrincipalProvider,
    ManagerSurfaceDefinition,
)
from atlanticus.web.manager.projection import (
    ConfigurationLifecycleWorkflow,
    DraftValidationResult,
    ManagerDraft,
    ProjectionAuditRecord,
    ProjectionExecutionResult,
    ProjectionIssue,
    ProjectionState,
    ProjectionStatus,
    ProjectionSummaryItem,
    RevisionHistoryEntry,
    RevisionHistoryWorkflow,
    SourcePublicationResult,
    SourceSnapshot,
    SourceVerificationResult,
    build_draft_revision,
    resolve_projection_state,
)
from atlanticus.web.manager.registry import ManagerModuleRegistry
from atlanticus.web.manager.surface import ManagerSurface

__all__ = [
    'ConfigurationLifecycleWorkflow',
    'DefaultManagerAuthorizationPolicy',
    'DraftValidationResult',
    'ManagerApplicationDefinition',
    'ManagerAuthorizationError',
    'ManagerAuthorizationPolicy',
    'ManagerBrand',
    'ManagerBrandMark',
    'ManagerDefinitionError',
    'ManagerDraft',
    'ManagerError',
    'ManagerHistoryPreviewRenderer',
    'ManagerLifecycleState',
    'ManagerModule',
    'ManagerModuleAccess',
    'ManagerModuleGroup',
    'ManagerModuleRegistry',
    'ManagerPrincipal',
    'ManagerPrincipalProvider',
    'ManagerSurface',
    'ManagerSurfaceDefinition',
    'ManagerProjectionCoordinator',
    'ManagerProjectionError',
    'ManagerSourceConflictError',
    'ProjectionAuditRecord',
    'ProjectionExecutionResult',
    'ProjectionIssue',
    'ProjectionState',
    'ProjectionStatus',
    'ProjectionSummaryItem',
    'RevisionHistoryEntry',
    'RevisionHistoryWorkflow',
    'SourcePublicationResult',
    'SourceSnapshot',
    'SourceVerificationResult',
    'build_draft_revision',
    'resolve_manager_lifecycle',
    'resolve_projection_state',
]
