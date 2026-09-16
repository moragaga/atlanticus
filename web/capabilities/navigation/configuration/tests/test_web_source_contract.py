from types import SimpleNamespace

import pytest

pytest.importorskip('dash')
from dash import Input, Output

from atlanticus.web.navigation.configuration.editor import build_initial_catalog
from atlanticus.web.navigation.configuration.exchange import build_navigation_configuration_digest
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.navigation.configuration.web import callbacks as navigation_callbacks
from atlanticus.web.navigation.configuration.web.callbacks import (
    register_navigation_admin_callbacks,
)
from atlanticus.web.navigation.configuration.web.ids import (
    CATALOG_STORE_ID,
    MOUNT_STORE_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
)
from atlanticus.web.navigation.configuration.web.models import NavigationAdminWebContext


class _CallbackRecorder:
    def __init__(self) -> None:
        self.callbacks: list[tuple[tuple[object, ...], dict[str, object], object]] = []

    def callback(self, *dependencies: object, **options: object):
        def register(function):
            self.callbacks.append((dependencies, options, function))
            return function

        return register

    def function_for_output(
        self,
        component_id: object,
        component_property: str,
        *,
        input_component_id: object | None = None,
    ):
        matches = []
        for dependencies, _options, function in self.callbacks:
            has_output = any(
                isinstance(dependency, Output)
                and dependency.component_id == component_id
                and dependency.component_property == component_property
                for dependency in dependencies
            )
            has_input = input_component_id is None or any(
                isinstance(dependency, Input)
                and dependency.component_id == input_component_id
                for dependency in dependencies
            )
            if has_output and has_input:
                matches.append(function)
        if len(matches) != 1:
            raise AssertionError(
                f"Expected one callback for {component_id!r}.{component_property}, found {len(matches)}"
            )
        return matches[0]

class _WorkspaceBinding:
    def __init__(self) -> None:
        self.saved: list[tuple[dict[str, object] | None, dict[str, object]]] = []

    def read(self, document: dict[str, object] | None) -> dict[str, object] | None:
        if not isinstance(document, dict):
            return None
        payload = document.get('payload')
        return dict(payload) if isinstance(payload, dict) else None

    def write(
        self,
        document: dict[str, object] | None,
        payload: dict[str, object],
    ) -> dict[str, object]:
        self.saved.append((document, dict(payload)))
        return {
            'schema_version': 2,
            'payload': dict(payload),
            'revision': build_navigation_configuration_digest(
                NavigationConfigurationCatalog.from_document(dict(payload))
            ),
        }


def _context(binding: _WorkspaceBinding) -> NavigationAdminWebContext:
    return NavigationAdminWebContext(
        workspace_payload_reader=binding.read,
        workspace_payload_writer=binding.write,
        draft_store_id='draft',
        saved_draft_store_id='saved-draft',
        draft_save_action_id={'type': 'save-draft', 'module': 'navigation'},
        editor_revision_store_id='editor-revision',
    )


def _callbacks(context: NavigationAdminWebContext) -> _CallbackRecorder:
    recorder = _CallbackRecorder()
    register_navigation_admin_callbacks(recorder, context)
    return recorder


def test_navigation_admin_rehydrates_workspace_payload() -> None:
    binding = _WorkspaceBinding()
    context = _context(binding)
    catalog = build_initial_catalog()
    load_browser_draft = _callbacks(context).function_for_output(
        CATALOG_STORE_ID,
        'data',
        input_component_id=MOUNT_STORE_ID,
    )

    catalog_document = load_browser_draft(1, {'payload': catalog.to_document()})

    assert catalog_document == catalog.to_document()

def test_navigation_admin_tracks_editor_revision_from_catalog() -> None:
    binding = _WorkspaceBinding()
    context = _context(binding)
    catalog = build_initial_catalog()
    track_editor_revision = _callbacks(context).function_for_output(
        context.editor_revision_store_id,
        'data',
    )

    revision = track_editor_revision(catalog.to_document())

    assert revision == build_navigation_configuration_digest(catalog)

def test_navigation_admin_save_delegates_workspace_persistence_without_remote_side_effects(
    monkeypatch,
) -> None:
    binding = _WorkspaceBinding()
    context = _context(binding)
    catalog = build_initial_catalog()
    save_navigation_draft = _callbacks(context).function_for_output(SAVE_RESULT_ID, 'children')
    current = {'schema_version': 2, 'payload': catalog.to_document()}

    monkeypatch.setattr(
        navigation_callbacks,
        'ctx',
        SimpleNamespace(triggered_id=SAVE_BUTTON_ID),
    )

    draft_document, saved_document, result = save_navigation_draft(
        1,
        None,
        catalog.to_document(),
        current,
    )

    assert saved_document == draft_document
    assert result is None
    assert binding.saved == [(current, catalog.to_document())]

