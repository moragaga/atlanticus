from __future__ import annotations

# Renderers específicos del contrato exact-source. Presentan identidad de release sin
# convertir SourceReleaseId o ConcurrencyToken a las revisiones legacy de ManagerDraft.

from dash import html

from atlanticus.web.manager.exact_source import ExactSourceReadResult
from atlanticus.web.manager.lifecycle import ManagerLifecycleState
from atlanticus.web.manager.models import ManagerPrincipal
from atlanticus.web.manager.workspace import ManagerSourceVerification, ManagerWorkspace


def build_exact_workspace_content(
    *,
    workspace: ManagerWorkspace | None,
    source: ExactSourceReadResult,
    validation: dict[str, object] | None,
    verification: ManagerSourceVerification | None,
    lifecycle: ManagerLifecycleState,
    principal: ManagerPrincipal,
) -> object:
    if workspace is None:
        return html.Section(
            [
                html.Strong('Trabajo local'),
                html.P('Todavía no hay un workspace exact-source guardado en este navegador.'),
            ],
            className='atlanticus-manager__workflow-group',
        )
    if workspace.owner_subject_id != principal.subject_id:
        return _error('El workspace local pertenece a otro usuario.')
    state = (
        'Cambios sin guardar'
        if lifecycle.dirty
        else ('Publicado' if lifecycle.published else 'No publicado')
    )
    validation_label = 'Pendiente'
    if lifecycle.validation_current:
        validation_label = 'Validado'
    elif validation and validation.get('draft_revision') == workspace.revision:
        validation_label = 'Con errores' if validation.get('valid') is False else 'Pendiente'
    verification_label = 'Pendiente'
    if lifecycle.published:
        verification_label = 'No requerida'
    elif verification is not None:
        verification_label = 'Verificada' if verification.publishable else 'Conflicto'
    return html.Section(
        [
            html.Strong('Trabajo local'),
            html.Div(
                [
                    _item('Estado', state),
                    _item('Revisión local', workspace.revision[:12]),
                    _item('Base Source', _release_label(workspace.base)),
                    _item('Source actual', _release_label(source.snapshot)),
                    _item('Validación', validation_label),
                    _item('Verificación', verification_label),
                ],
                className='atlanticus-manager__workflow-stage-grid',
            ),
            _issues(validation),
        ],
        className='atlanticus-manager__workflow-group',
    )


def build_exact_saved_workspace_content(
    *,
    workspace: ManagerWorkspace | None,
    source: ExactSourceReadResult | None,
    incompatible: bool = False,
) -> object:
    if incompatible:
        return html.Div(
            'Hay un workspace guardado antiguo o incompatible. Puedes descartarlo del navegador.',
            className='atlanticus-manager__message atlanticus-manager__message--notice',
        )
    if workspace is None:
        return html.Div(
            'No hay un workspace guardado para recuperar.',
            className='atlanticus-manager__saved-draft-empty',
        )
    source_changed = source is not None and _release_id(workspace.base) != _release_id(
        source.snapshot
    )
    return html.Div(
        [
            html.Strong(
                'Source cambió desde que se guardó este workspace.'
                if source_changed
                else 'Hay un workspace guardado disponible.'
            ),
            html.Div(
                [
                    _item('Revisión local', workspace.revision[:12]),
                    _item('Base Source', _release_label(workspace.base)),
                    *(
                        [_item('Source actual', _release_label(source.snapshot))]
                        if source_changed and source is not None
                        else []
                    ),
                ],
                className='atlanticus-manager__saved-draft-meta',
            ),
        ],
        className='atlanticus-manager__saved-draft-card',
    )


def build_exact_source_conflict_content(
    *,
    workspace: ManagerWorkspace,
    verification: ManagerSourceVerification,
) -> object:
    return html.Div(
        [
            html.Strong('Source cambió mientras estabas trabajando.'),
            html.P('Tu workspace se conserva sin cambios hasta que elijas cómo continuar.'),
            html.Div(
                [
                    _item('Base de tu workspace', _release_label(workspace.base)),
                    _item('Source actual', _release_label(verification.source)),
                ],
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
    messages = [
        str(item.get('message', '')).strip()
        for item in raw
        if isinstance(item, dict) and str(item.get('message', '')).strip()
    ]
    if not messages:
        return None
    return html.Ul([html.Li(message) for message in messages])


def _item(label: str, value: str) -> object:
    return html.Span([html.Small(label), html.Code(value)])


def _release_id(snapshot) -> object:
    if snapshot.current is None:
        return None
    return snapshot.current.release_ref.release_id


def _release_label(snapshot) -> str:
    if snapshot.current is None:
        return 'Sin publicación'
    return snapshot.current.release_ref.release_id.value[:12]


def _error(message: str) -> object:
    return html.Div(
        message,
        className='atlanticus-manager__message atlanticus-manager__message--error',
    )
