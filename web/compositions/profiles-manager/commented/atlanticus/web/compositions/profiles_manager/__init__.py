# API pública de la composición administrativa Profiles -> Manager.
from atlanticus.web.compositions.profiles_manager.composition import (
    PROFILES_CONFIGURATION_SOURCE_KEY,
    PROFILES_MANAGER_PROJECTION_SERVICE,
    PROFILES_MANAGER_SOURCE_SERVICE,
    PROFILES_MANAGER_VALIDATION_SERVICE,
    ProfilesManagerComposition,
    compose_profiles_manager,
)
from atlanticus.web.compositions.profiles_manager.providers import (
    compose_azure_profiles_manager,
    compose_local_profiles_manager,
)
from atlanticus.web.compositions.profiles_manager.workflows import (
    ProfilesAuditActorProvider,
    ProfilesManagerDraftValidationWorkflow,
    ProfilesManagerSourceWorkflow,
)
from atlanticus.web.compositions.profiles_manager.workspace import ProfilesManagerWorkspaceBinding

__all__ = [
    'PROFILES_CONFIGURATION_SOURCE_KEY',
    'PROFILES_MANAGER_PROJECTION_SERVICE',
    'PROFILES_MANAGER_SOURCE_SERVICE',
    'PROFILES_MANAGER_VALIDATION_SERVICE',
    'ProfilesAuditActorProvider',
    'ProfilesManagerComposition',
    'ProfilesManagerDraftValidationWorkflow',
    'ProfilesManagerSourceWorkflow',
    'ProfilesManagerWorkspaceBinding',
    'compose_azure_profiles_manager',
    'compose_local_profiles_manager',
    'compose_profiles_manager',
]
