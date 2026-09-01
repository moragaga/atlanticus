# Declara identificadores aislados por módulo para abrir, cerrar y confirmar la vista previa histórica.
# Los IDs pattern-matching mantienen separadas las revisiones y superficies del Manager.

LOCATION_ID = 'atlanticus-manager-location'
SUMMARY_ID = 'atlanticus-manager-summary'
SIDEBAR_ID = 'atlanticus-manager-sidebar'
SIDEBAR_BACKDROP_ID = 'atlanticus-manager-sidebar-backdrop'
SIDEBAR_TOGGLE_ID = 'atlanticus-manager-sidebar-toggle'
SIDEBAR_CLOSE_ID = 'atlanticus-manager-sidebar-close'
SIDEBAR_MODULES_ID = 'atlanticus-manager-sidebar-modules'
CONTENT_ID = 'atlanticus-manager-content'
REFRESH_BUTTON_ID = 'atlanticus-manager-refresh'
STATUS_STORE_ID = 'atlanticus-manager-status-store'
REFRESH_SIGNAL_ID = 'atlanticus-manager-refresh-signal'


def workflow_action_id(module_key: str, action: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-action',
        'module': module_key,
        'action': action,
    }


def workflow_result_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-result',
        'module': module_key,
    }


def workflow_revision_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-revision',
        'module': module_key,
    }


def workflow_status_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-status',
        'module': module_key,
    }


def workflow_draft_status_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-draft-status',
        'module': module_key,
    }


def workflow_conflict_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-conflict',
        'module': module_key,
    }


def workflow_conflict_details_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-conflict-details',
        'module': module_key,
    }


def workflow_history_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-history',
        'module': module_key,
    }


def module_status_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-module-status',
        'module': module_key,
    }


def workflow_refresh_signal_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-refresh-signal',
        'module': module_key,
    }


def workflow_projection_signal_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-projection-signal',
        'module': module_key,
    }


def workflow_draft_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-draft',
        'module': module_key,
    }


# Separa el checkpoint persistente del workspace activo para que localStorage nunca hidrate el editor por sí solo.
def workflow_saved_draft_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-saved-draft',
        'module': module_key,
    }


# Expone una superficie independiente para informar si existe un checkpoint recuperable y si su Source base cambió.
def workflow_saved_draft_status_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-saved-draft-status',
        'module': module_key,
    }


def workflow_validation_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-validation',
        'module': module_key,
    }


def workflow_source_verification_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-source-verification',
        'module': module_key,
    }


def workflow_editor_revision_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workflow-editor-revision',
        'module': module_key,
    }


def workflow_workspace_reset_signal_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workspace-reset-signal',
        'module': module_key,
    }


def workflow_workspace_command_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workspace-command',
        'module': module_key,
    }


def workflow_workspace_confirmation_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workspace-confirmation',
        'module': module_key,
    }


def workflow_workspace_confirmation_title_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workspace-confirmation-title',
        'module': module_key,
    }


def workflow_workspace_confirmation_message_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-workspace-confirmation-message',
        'module': module_key,
    }


def module_section_store_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-module-section-store',
        'module': module_key,
    }


def module_section_button_id(module_key: str, section: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-module-section-button',
        'module': module_key,
        'section': section,
    }


def module_section_panel_id(module_key: str, section: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-module-section-panel',
        'module': module_key,
        'section': section,
    }


def history_preview_open_id(
    module_key: str,
    revision: str,
    occurrence: str,
    *,
    saved_by: str,
    saved_at: str,
    current: bool,
    active: bool,
) -> dict[str, object]:
    return {
        'type': 'atlanticus-manager-history-preview-open',
        'module': module_key,
        'revision': revision,
        'occurrence': occurrence,
        'saved_by': saved_by,
        'saved_at': saved_at,
        'current': current,
        'active': active,
    }


def workflow_history_preview_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-history-preview',
        'module': module_key,
    }


def workflow_history_preview_store_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-history-preview-store',
        'module': module_key,
    }


def workflow_history_preview_heading_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-history-preview-heading',
        'module': module_key,
    }


def workflow_history_preview_meta_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-history-preview-meta',
        'module': module_key,
    }


def workflow_history_preview_body_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-history-preview-body',
        'module': module_key,
    }


def workflow_history_preview_close_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-history-preview-close',
        'module': module_key,
    }


def workflow_history_preview_load_id(module_key: str) -> dict[str, str]:
    return {
        'type': 'atlanticus-manager-history-preview-load',
        'module': module_key,
    }
