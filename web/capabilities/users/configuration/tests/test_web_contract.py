from pathlib import Path

ROOT = Path(__file__).parents[1]
WEB = ROOT / 'src/atlanticus/web/users/configuration/web'
CSS = ROOT / 'src/atlanticus/web/users/configuration/resources/css/00_users_admin.css'


def test_users_admin_ui_keeps_profiles_users_and_discovered_separate() -> None:
    layout = (WEB / 'layout.py').read_text(encoding='utf-8')

    assert "'Perfiles'" in layout
    assert "'Usuarios'" in layout
    assert "'Descubiertos'" in layout
    assert 'Local conserva identidades visuales fijas' in layout
    assert 'Administrator y Guest' in layout


def test_users_admin_dynamic_actions_require_real_clicks() -> None:
    callbacks = (WEB / 'callbacks.py').read_text(encoding='utf-8')

    assert '_pattern_click_is_real(trigger, edit_clicks, edit_ids)' in callbacks
    assert '_pattern_click_is_real(trigger, discovered_clicks, discovered_ids)' in callbacks
    assert '_pattern_click_is_real(trigger, clicks, delete_ids)' in callbacks
    assert 'n_clicks=0' in layout_source()


def test_users_admin_browser_draft_does_not_publish_source() -> None:
    callbacks = (WEB / 'callbacks.py').read_text(encoding='utf-8')

    assert '_browser_draft_document' in callbacks
    assert "Output(context.saved_draft_store_id, 'data', allow_duplicate=True)" in callbacks
    assert 'publish_catalog' not in callbacks
    assert 'project(' not in callbacks


def test_users_admin_uses_atlanticus_visual_tokens() -> None:
    css = CSS.read_text(encoding='utf-8')

    assert 'var(--atlanticus-manager-color-primary)' in css
    assert 'var(--atlanticus-manager-surface)' in css
    assert '--atlanticus-users-profile-background-color' in css
    assert '--atlanticus-users-profile-text-color' in css


def layout_source() -> str:
    return (WEB / 'layout.py').read_text(encoding='utf-8')


def test_users_admin_uses_native_browser_color_pickers() -> None:
    layout = layout_source()
    callbacks = (WEB / 'callbacks.py').read_text(encoding='utf-8')

    assert 'html.Input(' not in layout
    assert "type='color'" not in layout
    assert "type='text'" in layout
    assert "style={'display': 'none'}" in layout
    assert '_register_native_color_picker' in callbacks
    assert "picker.type = 'color'" in callbacks
    assert 'dash_clientside.set_props' in callbacks
    assert 'PROFILE_BACKGROUND_COLOR_ID' in layout
    assert 'PROFILE_TEXT_COLOR_ID' in layout
    assert 'ADMINISTRATOR_BACKGROUND_COLOR_ID' in layout
    assert 'ADMINISTRATOR_TEXT_COLOR_ID' in layout
    assert 'GUEST_BACKGROUND_COLOR_ID' in layout
    assert 'GUEST_TEXT_COLOR_ID' in layout


def test_users_admin_dynamic_layout_is_not_driven_by_global_manager_stores() -> None:
    callbacks = (WEB / 'callbacks.py').read_text(encoding='utf-8')

    assert "Input(context.draft_store_id, 'data')" in callbacks
    assert "Input(context.workflow_refresh_signal_id, 'data')" not in callbacks
    assert "Input(MOUNT_STORE_ID, 'data')" in callbacks
    assert "State(context.draft_store_id, 'data')" in callbacks
    assert "Output(context.editor_revision_store_id, 'data')" in callbacks
    assert 'build_users_configuration_digest(_catalog(catalog_data))' in callbacks


def test_users_admin_browser_draft_matches_manager_contract() -> None:
    callbacks = (WEB / 'callbacks.py').read_text(encoding='utf-8')

    assert '_BROWSER_DRAFT_SCHEMA_VERSION = 1' in callbacks
    assert "data.get('schema_version') not in {1, 2}" in callbacks


def test_users_admin_profile_text_color_wins_inside_avatar() -> None:
    css = CSS.read_text(encoding='utf-8')

    assert '.atlanticus-users-admin__profile-copy .atlanticus-users-admin__profile-avatar' in css
    assert 'color: var(--atlanticus-users-profile-text-color);' in css


def test_users_admin_labels_configuration_as_profiles_and_users() -> None:
    layout = layout_source()

    assert 'Importar archivo de Users' in layout
    assert 'Incluye perfiles y usuarios.' in layout
    assert 'Borrador de Users · perfiles y usuarios' in layout
    assert 'Guardar borrador de Users' in layout


def test_users_admin_import_refreshes_the_whole_users_catalog() -> None:
    callbacks = (WEB / 'callbacks.py').read_text(encoding='utf-8')

    assert "Output(CATALOG_STORE_ID, 'data', allow_duplicate=True)" in callbacks
    assert "Output(ADMINISTRATOR_TEXT_COLOR_ID, 'value', allow_duplicate=True)" in callbacks
    assert "Output(GUEST_TEXT_COLOR_ID, 'value', allow_duplicate=True)" in callbacks


def test_users_admin_keeps_source_revision_loaded_with_editor_content() -> None:
    layout = layout_source()
    callbacks = (WEB / 'callbacks.py').read_text(encoding='utf-8')

    assert 'SOURCE_REVISION_STORE_ID' in layout
    assert "State(SOURCE_REVISION_STORE_ID, 'data')" in callbacks
    assert '_current_source_revision' not in callbacks


def test_users_admin_rehydrates_editor_from_manager_draft_without_page_reload() -> None:
    callbacks = (WEB / 'callbacks.py').read_text(encoding='utf-8')

    load_start = callbacks.index('def load_browser_draft(')
    load_end = callbacks.index('def track_editor_revision(', load_start)
    load = callbacks[load_start:load_end]
    assert "Input(context.draft_store_id, 'data')" in callbacks[:load_start]
    assert 'base_source_revision' in load
    assert "Output(SOURCE_REVISION_STORE_ID, 'data')" in callbacks[:load_start]


def test_users_workspace_starts_empty_and_does_not_read_source_implicitly() -> None:
    layout = layout_source()
    callbacks = (WEB / 'callbacks.py').read_text(encoding='utf-8')

    assert 'context.services.administration.load_source()' not in layout
    assert 'catalog = _empty_catalog()' in layout
    assert 'data=None' in layout
    assert 'if draft_data is None:' in callbacks
    tracker = callbacks[
        callbacks.index("Output(context.editor_revision_store_id, 'data')") : callbacks.index(
            'def track_editor_revision('
        )
    ]
    assert 'prevent_initial_call=True' in tracker
