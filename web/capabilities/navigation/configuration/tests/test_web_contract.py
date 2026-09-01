from pathlib import Path

import pytest

pytest.importorskip('dash')

from atlanticus.web.navigation.configuration.adapters.memory import (
    MemoryNavigationConfigurationStore,
    MemoryNavigationProjectionRepository,
)
from atlanticus.web.navigation.configuration.services import (
    compose_navigation_configuration_services,
)
from atlanticus.web.navigation.configuration.web import (
    NavigationAdminWebContext,
    build_navigation_admin_configuration,
    create_navigation_admin_web_module,
)


def _context() -> NavigationAdminWebContext:
    source = MemoryNavigationConfigurationStore()
    services = compose_navigation_configuration_services(
        source=source,
        publisher=source,
        projection=MemoryNavigationProjectionRepository(),
        audit_actor_provider=lambda: 'tester',
    )
    return NavigationAdminWebContext(
        services=services,
        draft_store_id='draft',
        saved_draft_store_id='saved-draft',
        draft_save_action_id='save',
        workflow_refresh_signal_id='refresh',
        editor_revision_store_id='editor-revision',
        draft_owner_provider=lambda: 'tester',
    )


def test_navigation_admin_layout_builds_without_source() -> None:
    layout = build_navigation_admin_configuration(_context())
    assert layout is not None


def test_navigation_admin_web_module_owns_assets() -> None:
    module = create_navigation_admin_web_module(_context())
    assert module.name == 'atlanticus-navigation-configuration'
    assert module.asset_layers[0].name == 'atlanticus_navigation_configuration'


def test_navigation_configuration_web_does_not_import_users_or_ada() -> None:
    root = Path(__file__).parents[1] / 'src/atlanticus/web/navigation/configuration/web'
    product = '\n'.join(path.read_text(encoding='utf-8') for path in root.glob('*.py'))
    assert 'atlanticus.web.users' not in product
    assert 'ada.' not in product


def test_navigation_admin_rehydrates_manager_draft_and_tracks_editor_revision() -> None:
    callbacks = (
        Path(__file__).parents[1] / 'src/atlanticus/web/navigation/configuration/web/callbacks.py'
    ).read_text(encoding='utf-8')

    assert "Input(context.draft_store_id, 'data')" in callbacks
    assert "Output(context.saved_draft_store_id, 'data', allow_duplicate=True)" in callbacks
    assert "Output(SOURCE_REVISION_STORE_ID, 'data')" in callbacks
    assert "Output(context.editor_revision_store_id, 'data')" in callbacks
    assert 'build_navigation_configuration_digest(_catalog(catalog_data))' in callbacks


def test_navigation_workspace_starts_empty_and_does_not_read_source_implicitly() -> None:
    root = Path(__file__).parents[1] / 'src/atlanticus/web/navigation/configuration/web'
    layout = (root / 'layout.py').read_text(encoding='utf-8')
    callbacks = (root / 'callbacks.py').read_text(encoding='utf-8')

    assert 'context.services.administration.load_source()' not in layout
    assert '_structure_section(catalog)' in layout
    assert 'html.Div(navigation_structure(catalog), id=STRUCTURE_ID)' in layout
    assert "'Importar archivo de Navigation'" in layout
    assert 'if draft_data is None:' in callbacks
    assert (
        'prevent_initial_call=True'
        in callbacks[
            callbacks.index("Output(context.editor_revision_store_id, 'data')") : callbacks.index(
                'def track_editor_revision('
            )
        ]
    )


def test_navigation_structure_renderer_is_shared_by_layout_and_callbacks() -> None:
    root = Path(__file__).parents[1] / 'src/atlanticus/web/navigation/configuration/web'
    layout = (root / 'layout.py').read_text(encoding='utf-8')
    callbacks = (root / 'callbacks.py').read_text(encoding='utf-8')
    rendering = (root / 'rendering.py').read_text(encoding='utf-8')

    assert 'navigation_structure' in layout
    assert 'navigation_structure' in callbacks
    assert 'navigation_section_options' in callbacks
    assert 'def navigation_structure(' in rendering
    assert 'def navigation_section_options(' in rendering
    assert 'def _navigation_structure(' not in callbacks
