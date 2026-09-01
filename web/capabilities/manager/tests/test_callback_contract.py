import ast
from pathlib import Path


def _source() -> str:
    return (Path(__file__).parents[1] / 'src/atlanticus/web/manager/web/callbacks.py').read_text(
        encoding='utf-8'
    )


def test_workflow_callbacks_keep_match_scoped_outputs_per_module() -> None:
    source = _source()

    assert 'Output(REFRESH_SIGNAL_ID' not in source
    assert source.count("Input(REFRESH_SIGNAL_ID, 'data')") == 2
    assert source.count("Output(workflow_refresh_signal_id(MATCH), 'data'") == 6
    assert "Output(workflow_refresh_signal_id(ALL), 'data'" not in source
    assert "Input(workflow_refresh_signal_id(ALL), 'data')" in source


def test_workflow_refresh_does_not_rebuild_module_content() -> None:
    source = _source()
    start = source.index("Output(CONTENT_ID, 'children')")
    end = source.index("Output(module_section_panel_id(MATCH, 'content'), 'children')")
    route_callback = source[start:end]

    assert "Input(LOCATION_ID, 'pathname')" in route_callback
    assert "Input(STATUS_STORE_ID, 'data')" not in route_callback
    assert 'workflow_workspace_reset_signal_id' not in route_callback
    assert "Output(workflow_status_id(ALL), 'children')" in source
    assert "Output(workflow_action_id(ALL, 'project'), 'disabled')" in source


def test_lifecycle_actions_require_explicit_clicks_and_history_only_loads_draft() -> None:
    source = _source()

    assert 'def validate_configuration(' in source
    assert 'def verify_source_configuration(' in source
    assert 'def publish_configuration(' in source
    assert 'def project_configuration(' in source
    assert 'def hydrate_source_workspace(' in source
    assert 'def update_from_source(' in source
    assert 'def force_publish_configuration(' in source
    assert 'def manage_local_workspace(' in source
    assert 'def manage_saved_browser_draft(' in source
    assert 'def manage_history_preview(' in source
    assert 'def load_history_preview_as_draft(' in source
    assert 'restore_revision' not in source
    assert 'history_preview_open_id(' in source
    assert 'workflow_history_preview_load_id(MATCH)' in source
    assert 'not _pattern_click_is_real(trigger, clicks, preview_ids)' in source
    assert source.count('not _click_is_real(clicks)') >= 3
    assert 'ManagerDraft.create(' in source


def test_validation_does_not_refresh_source_but_source_actions_do() -> None:
    source = _source()
    validate_start = source.rindex('@app.callback(', 0, source.index('def validate_configuration('))
    verify_start = source.rindex(
        '@app.callback(', 0, source.index('def verify_source_configuration(')
    )
    publish_start = source.rindex('@app.callback(', 0, source.index('def publish_configuration('))
    update_start = source.rindex('@app.callback(', 0, source.index('def update_from_source('))
    project_start = source.rindex('@app.callback(', 0, source.index('def project_configuration('))
    project_end = source.index('\n\ndef _load_workflow_state', project_start)
    validate = source[validate_start:verify_start]
    verify = source[verify_start:publish_start]
    publish = source[publish_start:update_start]
    project = source[project_start:project_end]

    assert 'workflow_refresh_signal_id' not in validate
    assert 'workflow_refresh_signal_id' in verify
    assert 'workflow_refresh_signal_id' in publish
    assert 'workflow_refresh_signal_id' in project


def test_successful_publication_clears_the_persistent_browser_checkpoint() -> None:
    source = _source()

    publish_start = source.rindex('@app.callback(', 0, source.index('def publish_configuration('))
    publish_end = source.index('def hydrate_source_workspace(', publish_start)
    publish = source[publish_start:publish_end]
    force_start = source.rindex(
        '@app.callback(', 0, source.index('def force_publish_configuration(')
    )
    force_end = source.index('def manage_local_workspace(', force_start)
    force_publish = source[force_start:force_end]

    for callback in (publish, force_publish):
        assert "Output(workflow_saved_draft_id(MATCH), 'data', allow_duplicate=True)" in callback
        assert 'updated_draft.to_document(),\n            None,\n            None,' in callback or (
            'updated_draft.to_document(), None, None' in callback
        )


def test_successful_workflow_actions_use_state_instead_of_persistent_success_banners() -> None:
    source = _source()

    assert 'return None, validation' in source
    assert 'render_validation_result' not in source
    assert 'render_publication_result' not in source
    assert 'render_projection_result' not in source
    assert 'def clear_transient_workflow(' in source
    assert "Output(workflow_validation_id(ALL), 'data', allow_duplicate=True)" in source
    assert "Output(workflow_source_verification_id(ALL), 'data', allow_duplicate=True)" in source


def test_source_conflicts_refresh_status_without_automatic_projection() -> None:
    source = _source()

    assert 'ManagerSourceConflictError' in source
    assert 'coordinator.verify_source(' in source
    assert 'coordinator.load_current_source(' in source
    assert 'coordinator.force_publish_draft(' in source
    assert "workflow_action_id(MATCH, 'update-source')" in source
    assert "workflow_action_id(MATCH, 'keep-draft')" in source
    assert "workflow_action_id(MATCH, 'force-publish')" in source
    assert "'source_actor': status.source_audit.actor" in source
    assert "'source_occurred_at': (" in source
    force_start = source.index('def force_publish_configuration(')
    force_end = source.index('def manage_history_preview(', force_start)
    force_callback = source[force_start:force_end]
    assert 'coordinator.project(' not in force_callback


def test_explicit_lifecycle_requires_editor_revision_and_source_verification() -> None:
    source = _source()

    assert "Input(workflow_editor_revision_id(MATCH), 'data')" in source
    assert "Input(workflow_source_verification_id(MATCH), 'data')" in source
    assert "workflow_action_id(MATCH, 'verify-source')" in source
    assert 'resolve_manager_lifecycle(' in source
    assert 'verification.source_revision' in source
    assert (
        'draft.base_source_revision'
        not in source[
            source.index('def publish_configuration(') : source.index('def update_from_source(')
        ]
    )


def test_dirty_editor_hides_stale_validation_and_source_verification_state() -> None:
    source = _source()

    assert 'validation=None if lifecycle.dirty else validation_data' in source
    assert 'source_verification=None if lifecycle.dirty else verification' in source


def test_workspace_actions_restore_current_source_without_publishing_or_projecting() -> None:
    source = _source()

    assert "workflow_action_id(MATCH, 'load-source')" not in source
    assert "workflow_action_id(MATCH, 'discard-local')" in source
    assert "workflow_action_id(MATCH, 'reload')" in source
    assert 'workflow_workspace_command_id(MATCH)' in source
    assert 'workflow_workspace_reset_signal_id(MATCH)' in source
    start = source.index('def manage_local_workspace(')
    end = source.index('def manage_history_preview(', start)
    callback = source[start:end]
    assert '_load_current_source_workspace_draft(' in callback
    assert 'module.source_name' in callback
    assert 'draft_output = source_workspace.to_document()' in callback
    assert 'editor_output = source_workspace.revision' in callback
    assert 'int(refresh_signal or 0) + 1' in callback
    assert 'coordinator.project(' not in callback
    assert 'coordinator.publish_draft(' not in callback


def test_workspace_auto_loads_current_source_without_consulting_saved_browser_draft() -> None:
    source = _source()
    start = source.rindex('@app.callback(', 0, source.index('def hydrate_source_workspace('))
    end = source.index('def update_from_source(', start)
    callback = source[start:end]

    assert "Input(workflow_revision_id(MATCH), 'data')" in callback
    assert "State(workflow_revision_id(MATCH), 'id')" in callback
    assert "Output(workflow_result_id(MATCH), 'children')" in callback
    assert "Output(workflow_draft_id(MATCH), 'data')" in callback
    assert "Output(workflow_validation_id(MATCH), 'data')" in callback
    assert "Output(workflow_source_verification_id(MATCH), 'data')" in callback
    assert 'allow_duplicate=True' not in callback.split('def hydrate_source_workspace(', 1)[0]
    assert 'prevent_initial_call' not in callback.split('def hydrate_source_workspace(', 1)[0]
    assert "workflow_action_id(MATCH, 'load-source')" not in callback
    assert 'if _has_local_work(draft_data, editor_revision, principal):' in callback
    assert 'if _source_revision(revision_state) is None:' in callback
    assert 'coordinator.load_current_source(' in callback
    assert 'principal = definition.principal_provider()' in callback
    assert '_local_workspace_state(' in source
    assert 'workflow_saved_draft_id' not in callback


def test_validation_action_is_duplicate_safe_after_source_hydration_owns_initial_state() -> None:
    source = _source()
    start = source.rindex('@app.callback(', 0, source.index('def validate_configuration('))
    end = source.index('def verify_source_configuration(', start)
    callback = source[start:end]

    assert "Output(workflow_validation_id(MATCH), 'data', allow_duplicate=True)" in callback
    assert 'prevent_initial_call=True' in callback


def test_saved_browser_draft_requires_explicit_recovery_or_discard() -> None:
    source = _source()
    start = source.rindex('@app.callback(', 0, source.index('def manage_saved_browser_draft('))
    end = source.index('def validate_configuration(', start)
    callback = source[start:end]

    assert "workflow_action_id(MATCH, 'recover-saved-draft')" in callback
    assert "workflow_action_id(MATCH, 'discard-saved-draft')" in callback
    assert "State(workflow_saved_draft_id(MATCH), 'data')" in callback
    assert "Output(workflow_draft_id(MATCH), 'data', allow_duplicate=True)" in callback
    assert 'draft.to_document()' in callback
    assert 'draft.base_source_revision != source_revision' in callback
    assert 'coordinator.publish_draft(' not in callback
    assert 'coordinator.project(' not in callback


def test_workspace_reset_rebuilds_only_the_editor_surface_without_loading_source() -> None:
    source = _source()
    reset_start = source.index("Output(module_section_panel_id(MATCH, 'content'), 'children')")
    reset_end = source.index("Output(module_section_store_id(MATCH), 'data')", reset_start)
    reset_callback = source[reset_start:reset_end]

    assert "Input(workflow_workspace_reset_signal_id(MATCH), 'data')" in reset_callback
    assert 'return module.layout(services)' in reset_callback
    assert 'build_module_content(' not in reset_callback
    assert 'coordinator.get_status(' not in reset_callback
    assert 'coordinator.list_history(' not in reset_callback


def test_history_preview_does_not_mutate_workspace_until_confirmed() -> None:
    source = _source()
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    preview_callback = ast.get_source_segment(source, functions['manage_history_preview']) or ''
    load_callback = ast.get_source_segment(source, functions['load_history_preview_as_draft']) or ''

    assert 'coordinator.load_history_revision(' in preview_callback
    assert 'module.history_preview_renderer' in preview_callback
    assert 'ManagerDraft.create(' not in preview_callback
    assert 'workflow_draft_id' not in preview_callback
    assert 'ManagerDraft.create(' in load_callback
    assert '_history_preview_payload(' in load_callback
    assert 'coordinator.load_history_revision(' not in load_callback


def test_conflict_resolution_can_keep_local_draft_without_writing_source() -> None:
    source = _source()
    start = source.index('def update_from_source(')
    end = source.index('def force_publish_configuration(', start)
    callback = source[start:end]

    assert "action == 'keep-draft'" in callback
    assert 'draft.with_base_source_revision(verification.source_revision)' in callback
    assert 'coordinator.publish_draft(' not in callback
    assert 'coordinator.force_publish_draft(' not in callback
    assert 'coordinator.project(' not in callback
    assert 'module.source_name' in callback
