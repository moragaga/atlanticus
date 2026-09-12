from types import SimpleNamespace

import pytest

pytest.importorskip('dash')

from atlanticus.web.manager.projection import ManagerDraft
from atlanticus.web.navigation.configuration.adapters.memory import (
    MemoryNavigationConfigurationStore,
    MemoryNavigationProjectionRepository,
)
from atlanticus.web.navigation.configuration.editor import build_initial_catalog
from atlanticus.web.navigation.configuration.services import (
    compose_navigation_configuration_services,
)
from atlanticus.web.navigation.configuration.web import callbacks as navigation_callbacks
from atlanticus.web.navigation.configuration.web.callbacks import (
    _browser_draft_document,
    register_navigation_admin_callbacks,
)
from atlanticus.web.navigation.configuration.web.ids import SAVE_BUTTON_ID
from atlanticus.web.navigation.configuration.web.models import NavigationAdminWebContext


class _CallbackRecorder:
    def __init__(self) -> None:
        self.callbacks: dict[str, tuple[tuple[object, ...], dict[str, object], object]] = {}

    def callback(self, *dependencies: object, **options: object):
        def register(function):
            self.callbacks[function.__name__] = (dependencies, options, function)
            return function

        return register


def _context() -> tuple[
    NavigationAdminWebContext,
    MemoryNavigationConfigurationStore,
    MemoryNavigationProjectionRepository,
]:
    source = MemoryNavigationConfigurationStore()
    projection = MemoryNavigationProjectionRepository()
    services = compose_navigation_configuration_services(
        source=source,
        publisher=source,
        projection=projection,
        audit_actor_provider=lambda: 'tester',
    )
    return (
        NavigationAdminWebContext(
            services=services,
            draft_store_id='draft',
            saved_draft_store_id='saved-draft',
            draft_save_action_id='workflow-save-draft',
            workflow_refresh_signal_id='workflow-refresh',
            editor_revision_store_id='editor-revision',
            draft_owner_provider=lambda: 'tester',
        ),
        source,
        projection,
    )


def _callbacks(context: NavigationAdminWebContext) -> _CallbackRecorder:
    recorder = _CallbackRecorder()
    register_navigation_admin_callbacks(recorder, context)
    return recorder


def test_navigation_admin_rehydrates_manager_draft_with_source_revision() -> None:
    context, _source, _projection = _context()
    catalog = build_initial_catalog()
    draft = _browser_draft_document(
        catalog=catalog,
        owner_subject_id='tester',
        base_source_revision='source-9',
    )
    load_browser_draft = _callbacks(context).callbacks['load_browser_draft'][2]

    catalog_document, source_revision = load_browser_draft(1, draft)

    assert catalog_document == catalog.to_document()
    assert source_revision == 'source-9'


def test_navigation_admin_tracks_editor_revision_from_catalog() -> None:
    context, _source, _projection = _context()
    catalog = build_initial_catalog()
    track_editor_revision = _callbacks(context).callbacks['track_editor_revision'][2]

    revision = track_editor_revision(catalog.to_document())

    assert isinstance(revision, str)
    assert revision
    assert (
        revision
        == ManagerDraft.from_document(
            _browser_draft_document(
                catalog=catalog,
                owner_subject_id='tester',
                base_source_revision=None,
            )
        ).revision
    )


def test_navigation_admin_save_draft_is_local_and_does_not_publish_or_project(
    monkeypatch,
) -> None:
    context, source, projection = _context()
    catalog = build_initial_catalog()
    save_navigation_draft = _callbacks(context).callbacks['save_navigation_draft'][2]

    monkeypatch.setattr(
        navigation_callbacks,
        'ctx',
        SimpleNamespace(triggered_id=SAVE_BUTTON_ID),
    )

    draft_document, saved_document, result = save_navigation_draft(
        1,
        None,
        catalog.to_document(),
        'source-15',
        None,
    )

    draft = ManagerDraft.from_document(draft_document)

    assert saved_document == draft_document
    assert result is None
    assert draft.owner_subject_id == 'tester'
    assert draft.base_source_revision == 'source-15'
    assert draft.payload == catalog.to_document()
    assert source.fetch_bundle() is None
    assert projection.load() is None
