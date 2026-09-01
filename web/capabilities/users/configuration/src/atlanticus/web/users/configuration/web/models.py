from collections.abc import Callable
from dataclasses import dataclass

from atlanticus.web.users.configuration.services import UsersConfigurationServices


@dataclass(frozen=True, slots=True)
class UsersAdminWebContext:
    services: UsersConfigurationServices
    draft_store_id: object
    saved_draft_store_id: object
    draft_save_action_id: object
    workflow_refresh_signal_id: object
    editor_revision_store_id: object
    draft_owner_provider: Callable[[], str]
    can_manage: Callable[[], bool] = lambda: True
    source_name: str = 'Source'
    projection_name: str = 'Projection'
