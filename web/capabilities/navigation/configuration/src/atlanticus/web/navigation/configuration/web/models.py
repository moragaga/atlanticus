from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from atlanticus.web.navigation.configuration.profiles import NavigationProfileOption
from atlanticus.web.navigation.configuration.services import NavigationConfigurationServices

NavigationProfileOptionsProvider = Callable[[], tuple[NavigationProfileOption, ...]]


@dataclass(frozen=True, slots=True)
class NavigationAdminWebContext:
    services: NavigationConfigurationServices
    draft_store_id: object
    saved_draft_store_id: object
    draft_save_action_id: object
    workflow_refresh_signal_id: object
    editor_revision_store_id: object
    draft_owner_provider: Callable[[], str]
    can_manage: Callable[[], bool] = lambda: True
    source_name: str = 'Source'
    projection_name: str = 'Projection'
    profile_options_provider: NavigationProfileOptionsProvider | None = None
