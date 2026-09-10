from datetime import UTC, datetime
from importlib.resources import files

from dash.development.base_component import Component

from atlanticus.web.manager import (
    ManagerDraft,
    ManagerModule,
    ProjectionAuditRecord,
    ProjectionIssue,
    ProjectionStatus,
    RevisionHistoryEntry,
)
from atlanticus.web.manager.web.layout import (
    _build_validation_issues,
    build_saved_draft_content,
    build_workflow_history_content,
)


def _walk(component: object) -> list[Component]:
    found: list[Component] = []
    if isinstance(component, Component):
        found.append(component)
        children = getattr(component, 'children', None)
        if isinstance(children, (list, tuple)):
            for child in children:
                found.extend(_walk(child))
        elif children is not None:
            found.extend(_walk(children))
    return found


def _classes(component: object) -> tuple[str, ...]:
    return tuple(
        str(node.className)
        for node in _walk(component)
        if getattr(node, 'className', None)
    )


def test_validation_issues_are_compact_and_bounded() -> None:
    issues = tuple(
        ProjectionIssue(
            code='kpi_definition.missing',
            message=f"KPI definition 'kpi_{index:04d}' is missing",
            level='warning',
            path='definitions',
        )
        for index in range(500)
    )

    component = _build_validation_issues(issues)
    nodes = _walk(component)
    classes = _classes(component)

    assert component is not None
    assert component.__class__.__name__ == 'Div'
    assert not any(node.__class__.__name__ == 'Ul' for node in nodes)
    assert sum('atlanticus-manager__issue--warning' in value for value in classes) == 8
    assert any(node.__class__.__name__ == 'Details' for node in nodes)
    assert any(node.__class__.__name__ == 'Summary' for node in nodes)
    assert any(
        '492 observaciones adicionales' in str(getattr(node, 'children', ''))
        for node in nodes
    )


def test_saved_draft_uses_one_card_without_nested_empty_surface() -> None:
    draft = ManagerDraft.create(
        owner_subject_id='local',
        payload={'value': 1},
        base_source_revision=None,
    )

    component = build_saved_draft_content(
        draft=draft,
        source_revision=None,
    )
    classes = _classes(component)

    assert component.className == 'atlanticus-manager__saved-draft-card'
    assert 'atlanticus-manager__workflow-empty' not in classes
    assert 'atlanticus-manager__conflict-revisions' not in classes
    assert 'atlanticus-manager__saved-draft-meta' in classes


def test_history_rows_carry_semantic_labels_for_mobile() -> None:
    audit = ProjectionAuditRecord(
        actor='ui-preview',
        occurred_at=datetime(2026, 9, 10, 17, 52, 58, tzinfo=UTC),
    )
    status = ProjectionStatus(
        source_revision='source-r1',
        source_audit=audit,
        active_revision='projection-r1',
        active_source_revision='source-r1',
        projection_audit=audit,
    )
    module = ManagerModule(
        key='kpi-definitions',
        group_key='configuration',
        title='Definiciones KPI',
        route='/kpi-definitions',
        order=50,
        layout=lambda _services: None,
        workflow_service='workflow',
        history_preview_renderer=lambda _payload: None,
    )
    history = (
        RevisionHistoryEntry(
            revision='revision-1234567890',
            saved_by='ui-preview',
            saved_at=datetime(2026, 9, 10, 17, 52, 58, tzinfo=UTC),
            active=True,
            current=True,
        ),
    )

    component = build_workflow_history_content(
        module=module,
        status=status,
        history=history,
        can_load_history=True,
        error=None,
    )
    labels = [
        node.children
        for node in _walk(component)
        if getattr(node, 'className', None)
        == 'atlanticus-manager__history-cell-label'
    ]

    assert labels == ['Revisión', 'Publicado por', 'Fecha', 'Estado', 'Acción']


def test_workflow_css_contains_final_mobile_contracts() -> None:
    css = (
        files('atlanticus.web.manager')
        .joinpath('resources/css/30_workflow.css')
        .read_text(encoding='utf-8')
    )

    assert '.atlanticus-manager__saved-draft-card {' in css
    assert '.atlanticus-manager__issues-disclosure {' in css
    assert '.atlanticus-manager__history-cell-label {' in css
    assert (
        '.atlanticus-manager__history-row:not('
        '.atlanticus-manager__history-row--header)'
    ) in css
