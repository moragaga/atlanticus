# Expone History durable de Users a Manager conservando SourceReleaseRef y HistoryPage canónicos.

from __future__ import annotations

from atlanticus.web.manager import ExactSourceHistoryReadResult
from atlanticus.web.source.models import HistoryPage, SourceReleaseRef
from atlanticus.web.users.configuration.admin_composition import (
    UsersProfilesAdministrationService,
)


class UsersManagerExactSourceHistoryWorkflow:
    def __init__(self, *, administration: UsersProfilesAdministrationService) -> None:
        self._administration = administration

    def list_history_exact(self, *, limit: int = 20) -> HistoryPage:
        # La paginación y la identidad pertenecen a Source; no se fabrican revisiones Manager.
        return self._administration.query_history(page_size=limit)

    def load_history_release_exact(
        self,
        release_ref: SourceReleaseRef,
    ) -> ExactSourceHistoryReadResult:
        # Lee exactamente la release seleccionada y devuelve payload canónico de Users+Profiles.
        configuration = self._administration.load_history_release(release_ref)
        return ExactSourceHistoryReadResult(
            release_ref=release_ref,
            payload=configuration.to_document(),
        )


def create_users_manager_exact_source_history_workflow(
    *,
    administration: UsersProfilesAdministrationService,
) -> UsersManagerExactSourceHistoryWorkflow:
    return UsersManagerExactSourceHistoryWorkflow(administration=administration)
