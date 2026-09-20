from __future__ import annotations

from dash import html

from atlanticus.web.manager.lifecycle import ManagerLifecycleState
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.manager.source import SourceReadResult
from atlanticus.web.manager.workspace import ManagerSourceVerification, ManagerWorkspace


def build_workspace_content(
    *,
    workspace: ManagerWorkspace | None,
    source: SourceReadResult,
    validation: dict[str, object] | None,
    verification: ManagerSourceVerification | None,
    lifecycle: ManagerLifecycleState,
    principal: ManagerPrincipal,
) -> object:
    if workspace is None:
        return html.Section(
            [
                _group_header(
                    'Trabajo local',
                    'Estado del trabajo local guardado en este navegador.',
                ),
                html.Div(
                    'Todavía no hay un workspace guardado en este navegador.',
                    className='atlanticus-manager__workflow-empty',
                ),
            ],
            className='atlanticus-manager__workflow-group',
        )
    if workspace.owner_subject_id != principal.subject_id:
        return _error('El workspace local pertenece a otro usuario.')
    state = 'Cambios sin guardar' if lifecycle.dirty else ('Publicado' if lifecycle.published else 'No publicado')
    validation_label = 'Validado' if lifecycle.validation_current else 'Pendiente'
    if validation and validation.get('draft_revision') == workspace.revision and validation.get('valid') is False:
        validation_label = 'Con errores'
    verification_label = 'No requerida' if lifecycle.published else 'Pendiente'
    if verification is not None:
        verification_label = 'Verificada' if verification.publishable else 'Conflicto'
    return html.Section(
        [
            _group_header(
                'Trabajo local',
                'Estado del trabajo local antes de publicar en Source.',
            ),
            html.Div(
                [
                    _stage(
                        '1',
                        'Workspace del navegador',
                        state,
                        (('Revisión local', workspace.revision[:12]),),
                    ),
                    _stage(
                        '2',
                        'Source',
                        'Trazabilidad de publicación',
                        (
                            ('Base Source', _release_label(workspace.base)),
                            ('Source actual', _release_label(source.snapshot)),
                        ),
                    ),
                    _stage(
                        '3',
                        'Control previo',
                        'Antes de publicar',
                        (
                            ('Validación', validation_label),
                            ('Verificación', verification_label),
                        ),
                    ),
                ],
                className='atlanticus-manager__workflow-stage-grid',
            ),
            _issues(validation),
        ],
        className='atlanticus-manager__workflow-group',
    )


def build_saved_workspace_content(
    *,
    workspace: ManagerWorkspace | None,
    source: SourceReadResult | None,
    incompatible: bool = False,
) -> object:
    if incompatible:
        return html.Div(
            'Hay un workspace guardado antiguo o incompatible. Puedes descartarlo del navegador.',
            className='atlanticus-manager__message atlanticus-manager__message--notice',
        )
    if workspace is None:
        return html.Div('No hay un workspace guardado para recuperar.', className='atlanticus-manager__saved-draft-empty')
    source_changed = source is not None and workspace.base.current != source.snapshot.current
    return html.Div(
        [
            html.Strong('Source cambió desde que se guardó este workspace.' if source_changed else 'Hay un workspace guardado disponible.'),
            html.Div(
                [
                    _item('Revisión local', workspace.revision[:12]),
                    _item('Base Source', _release_label(workspace.base)),
                    *([_item('Source actual', _release_label(source.snapshot))] if source_changed and source is not None else []),
                ],
                className='atlanticus-manager__saved-draft-meta',
            ),
        ],
        className='atlanticus-manager__saved-draft-card',
    )


def build_source_conflict_content(
    *,
    workspace: ManagerWorkspace,
    verification: ManagerSourceVerification,
) -> object:
    return html.Div(
        [
            html.Strong('Source cambió mientras estabas trabajando.'),
            html.P('Tu workspace se conserva sin cambios hasta que elijas cómo continuar.'),
            html.Div(
                [_item('Base de tu workspace', _release_label(workspace.base)), _item('Source actual', _release_label(verification.source))],
                className='atlanticus-manager__conflict-revisions',
            ),
        ],
        className='atlanticus-manager__conflict-details',
    )


def _issues(validation: dict[str, object] | None) -> object | None:
    if not validation:
        return None
    raw = validation.get('issues')
    if not isinstance(raw, list) or not raw:
        return None
    messages = [str(item.get('message', '')).strip() for item in raw if isinstance(item, dict) and str(item.get('message', '')).strip()]
    return html.Ul([html.Li(message) for message in messages]) if messages else None


def _group_header(title: str, description: str) -> object:
    return html.Header(
        [html.Div([html.H3(title), html.P(description)])],
        className='atlanticus-manager__workflow-group-header',
    )


def _stage(
    step: str,
    title: str,
    subtitle: str,
    items: tuple[tuple[str, str], ...],
) -> object:
    return html.Article(
        [
            html.Header(
                [
                    html.Span(step, className='atlanticus-manager__workflow-step-number'),
                    html.Div([html.H4(title), html.P(subtitle)]),
                ],
                className='atlanticus-manager__workflow-stage-header',
            ),
            html.Div(
                [
                    html.Div(
                        [html.Span(label), html.Strong(value)],
                        className='atlanticus-manager__workflow-stage-item',
                    )
                    for label, value in items
                ],
                className='atlanticus-manager__workflow-stage-items',
            ),
        ],
        className='atlanticus-manager__workflow-stage-card',
    )


def _item(label: str, value: str) -> object:
    return html.Span([html.Small(label), html.Code(value)])


def _release_label(snapshot) -> str:
    if snapshot.current is None:
        return 'Sin publicación'
    return snapshot.current.release_ref.release_id.value[:12]


def _error(message: str) -> object:
    return html.Div(message, className='atlanticus-manager__message atlanticus-manager__message--error')
