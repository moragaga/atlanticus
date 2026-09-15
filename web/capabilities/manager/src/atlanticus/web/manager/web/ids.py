LOCATION_ID = 'atlanticus-manager-location'
SUMMARY_ID = 'atlanticus-manager-summary'
SIDEBAR_ID = 'atlanticus-manager-sidebar'
SIDEBAR_BACKDROP_ID = 'atlanticus-manager-sidebar-backdrop'
SIDEBAR_TOGGLE_ID = 'atlanticus-manager-sidebar-toggle'
SIDEBAR_CLOSE_ID = 'atlanticus-manager-sidebar-close'
SIDEBAR_MODULES_ID = 'atlanticus-manager-sidebar-modules'
CONTENT_ID = 'atlanticus-manager-content'
STATUS_STORE_ID = 'atlanticus-manager-status-store'
REFRESH_SIGNAL_ID = 'atlanticus-manager-refresh-signal'
HOME_ID = 'atlanticus-manager-home'
HOME_CARDS_ID = 'atlanticus-manager-home-cards'
HOME_PAGE_STORE_ID = 'atlanticus-manager-home-page-store'
HOME_PREVIOUS_ID = 'atlanticus-manager-home-previous'
HOME_NEXT_ID = 'atlanticus-manager-home-next'
HOME_PAGE_LABEL_ID = 'atlanticus-manager-home-page-label'


def _module_id(kind: str, module_key: str) -> dict[str, str]:
    return {'type': kind, 'module': module_key}


def workflow_action_id(module_key: str, action: str) -> dict[str, str]:
    return {'type': 'atlanticus-manager-workflow-action', 'module': module_key, 'action': action}


def workflow_result_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workflow-result', module_key)


def workflow_status_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workflow-status', module_key)


def workflow_draft_status_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workflow-draft-status', module_key)


def workflow_conflict_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workflow-conflict', module_key)


def workflow_conflict_details_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workflow-conflict-details', module_key)


def workflow_history_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workflow-history', module_key)


def module_status_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-module-status', module_key)


def workflow_refresh_signal_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workflow-refresh-signal', module_key)


def workflow_projection_signal_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workflow-projection-signal', module_key)


def workflow_draft_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workflow-draft', module_key)


def workflow_saved_draft_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workflow-saved-draft', module_key)


def workflow_saved_draft_status_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workflow-saved-draft-status', module_key)


def workflow_validation_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workflow-validation', module_key)


def workflow_source_verification_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workflow-source-verification', module_key)


def workflow_editor_revision_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workflow-editor-revision', module_key)


def workflow_workspace_reset_signal_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workspace-reset-signal', module_key)


def workflow_workspace_command_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workspace-command', module_key)


def workflow_workspace_confirmation_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workspace-confirmation', module_key)


def workflow_workspace_confirmation_title_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workspace-confirmation-title', module_key)


def workflow_workspace_confirmation_message_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-workspace-confirmation-message', module_key)


def module_section_store_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-module-section-store', module_key)


def module_section_button_id(module_key: str, section: str) -> dict[str, str]:
    return {'type': 'atlanticus-manager-module-section-button', 'module': module_key, 'section': section}


def module_section_panel_id(module_key: str, section: str) -> dict[str, str]:
    return {'type': 'atlanticus-manager-module-section-panel', 'module': module_key, 'section': section}


def history_preview_open_id(
    module_key: str,
    release_id: str,
    published_at_utc: str,
    occurrence: str,
    *,
    current: bool,
    active: bool,
) -> dict[str, object]:
    return {
        'type': 'atlanticus-manager-history-preview-open',
        'module': module_key,
        'release_id': release_id,
        'published_at_utc': published_at_utc,
        'occurrence': occurrence,
        'current': current,
        'active': active,
    }


def workflow_history_preview_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-history-preview', module_key)


def workflow_history_preview_store_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-history-preview-store', module_key)


def workflow_history_preview_heading_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-history-preview-heading', module_key)


def workflow_history_preview_meta_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-history-preview-meta', module_key)


def workflow_history_preview_body_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-history-preview-body', module_key)


def workflow_history_preview_close_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-history-preview-close', module_key)


def workflow_history_preview_load_id(module_key: str) -> dict[str, str]:
    return _module_id('atlanticus-manager-history-preview-load', module_key)
