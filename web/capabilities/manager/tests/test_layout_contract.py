from pathlib import Path


def test_manager_css_recovers_atlanticus_identity_and_true_offcanvas_layout() -> None:
    root = Path(__file__).parents[1] / 'src/atlanticus/web/manager/resources/css'
    tokens = (root / '00_tokens.css').read_text(encoding='utf-8')
    layout = (root / '10_manager.css').read_text(encoding='utf-8')

    assert '#0D1B2A' in tokens
    assert '#C9A24B' in tokens
    assert '#F5F1E6' in tokens
    assert "'Inter'" in tokens
    assert "'Cinzel'" in tokens
    assert 'transform: translateX(-105%)' in layout
    assert '.atlanticus-manager__sidebar--open' in layout
    assert 'width: min(100%, 118rem)' in layout


def test_manager_lifecycle_exposes_draft_validate_publish_and_project() -> None:
    root = Path(__file__).parents[1]
    layout = (root / 'src/atlanticus/web/manager/web/layout.py').read_text(encoding='utf-8')

    assert "id=workflow_draft_id(module.key),\n                    storage_type='memory'" in layout
    assert (
        "id=workflow_saved_draft_id(module.key),\n                    storage_type='local'"
        in layout
    )
    assert "workflow_action_id(module.key, 'save-draft')" in layout
    assert "workflow_action_id(module.key, 'validate')" in layout
    assert "workflow_action_id(module.key, 'verify-source')" in layout
    assert "workflow_action_id(module.key, 'publish')" in layout
    assert "workflow_action_id(module.key, 'project')" in layout
    assert "workflow_action_id(module.key, 'load-source')" not in layout
    assert "workflow_action_id(module.key, 'discard-local')" in layout
    assert "workflow_action_id(module.key, 'reload')" in layout
    assert "workflow_action_id(module.key, 'recover-saved-draft')" in layout
    assert "workflow_action_id(module.key, 'discard-saved-draft')" in layout
    assert "workflow_action_id(module.key, 'update-source')" in layout
    assert "workflow_action_id(module.key, 'force-publish')" in layout
    assert "f'Verificar {module.source_name}'" in layout
    assert "f'Guardar en {module.source_name}'" in layout
    assert "f'Usar versión de {module.source_name}'" in layout
    assert "workflow_action_id(module.key, 'keep-draft')" in layout
    assert "'Mantener mi borrador'" in layout
    assert "f'Proyectar en {module.projection_name}'" in layout
    assert 'module.force_publish_enabled' in layout


def test_source_audit_is_specific_and_history_opens_preview_before_loading_draft() -> None:
    root = Path(__file__).parents[1]
    layout = (root / 'src/atlanticus/web/manager/web/layout.py').read_text(encoding='utf-8')

    assert "'Última publicación'" in layout
    assert "'Última proyección'" in layout
    assert "'Última validación'" not in layout
    assert "'Ver revisión'" in layout
    assert "'Cargar como borrador'" in layout
    assert 'history_preview_open_id(' in layout
    assert 'workflow_history_preview_load_id(module.key)' in layout
    assert 'history_load_id(' not in layout


def test_header_keeps_atlanticus_identity_without_duplicate_user_identity() -> None:
    root = Path(__file__).parents[1]
    layout = (root / 'src/atlanticus/web/manager/web/layout.py').read_text(encoding='utf-8')
    css = (root / 'src/atlanticus/web/manager/resources/css/10_manager.css').read_text(
        encoding='utf-8'
    )

    assert "for role in ('framework', 'organization')" in layout
    assert 'principal.display_name' not in layout
    assert '.atlanticus-manager__brand-supporting' in css
    assert 'font-family: var(--atlanticus-manager-font-brand) !important' in css


def test_traceability_is_grouped_as_a_five_stage_pipeline() -> None:
    root = Path(__file__).parents[1]
    layout = (root / 'src/atlanticus/web/manager/web/layout.py').read_text(encoding='utf-8')
    css = (root / 'src/atlanticus/web/manager/resources/css/10_manager.css').read_text(
        encoding='utf-8'
    )

    assert "title='Borrador del navegador'" in layout
    assert "title='Validación'" in layout
    assert "title='Verificación de fuente'" in layout
    assert "title='Fuente de verdad'" in layout
    assert "title='Proyección runtime'" in layout
    assert "'Flujo de publicación'" in layout
    assert "html.Span('Revisión')" in layout
    assert "html.Span('Publicado por')" in layout
    assert '.atlanticus-manager__workflow-stage-grid' in css
    assert '.atlanticus-manager__workflow-action-grid' in css
    assert '.atlanticus-manager__history-row--header' in css


def test_source_conflict_is_rendered_as_functional_state_with_actor_and_revisions() -> None:
    root = Path(__file__).parents[1]
    layout = (root / 'src/atlanticus/web/manager/web/layout.py').read_text(encoding='utf-8')

    assert 'source_verification.publishable' in layout
    assert "'La fuente cambió mientras estabas trabajando.'" in layout
    assert "'Base de tu borrador'" in layout
    assert "'Fuente actual'" in layout
    assert 'source_actor' in layout
    assert 'source_occurred_at' in layout


def test_manager_tracks_editor_revision_and_source_verification_as_transient_state() -> None:
    root = Path(__file__).parents[1]
    layout = (root / 'src/atlanticus/web/manager/web/layout.py').read_text(encoding='utf-8')

    assert 'workflow_editor_revision_id(module.key)' in layout
    assert 'workflow_source_verification_id(module.key)' in layout
    assert "storage_type='memory'" in layout
    assert "'Cambios sin guardar'" in layout


def test_workspace_actions_explain_refresh_and_post_publish_verification() -> None:
    root = Path(__file__).parents[1]
    layout = (root / 'src/atlanticus/web/manager/web/layout.py').read_text(encoding='utf-8')
    css = (root / 'src/atlanticus/web/manager/resources/css/10_manager.css').read_text(
        encoding='utf-8'
    )

    assert "'Workspace local'" in layout
    assert "'Descartar cambios locales'" in layout
    assert "'Recargar'" in layout
    assert "'Recuperar borrador'" in layout
    assert "'Descartar borrador guardado'" in layout
    assert "'La configuración publicada se mantiene visible hasta que elijas recuperar '" in layout
    assert "f'Recargar restaura la versión actual de {module.source_name} y vuelve '" in layout
    assert "'a consultar fuente, historial y proyección.'" in layout
    assert "f'Cargar configuración desde {module.source_name}'" not in layout
    assert "'No requerida' if draft.revision == source_revision else 'Pendiente'" in layout
    assert 'workflow_workspace_confirmation_id(module.key)' in layout
    assert '.atlanticus-manager__workspace-confirm' in css


def test_history_preview_is_non_destructive_until_explicit_load() -> None:
    root = Path(__file__).parents[1]
    layout = (root / 'src/atlanticus/web/manager/web/layout.py').read_text(encoding='utf-8')

    assert "'Vista previa histórica'" in layout
    assert "'Cargar esta revisión reemplazará el trabajo local actual del '" in layout
    assert 'workflow_history_preview_store_id(module.key)' in layout
    assert 'module.history_preview_renderer is not None' in layout
    assert 'hidden=True' in layout
