from types import SimpleNamespace

from ada_command_center.tools.discovery_cosmos.manager import (
    AdoptedToolCatalog,
    ToolCandidateSummary,
    ToolCatalogManagerConflictError,
    ToolCatalogReview,
    ToolConnectionSummary,
)
from ada_command_center.web.tools.catalog_manager import manager as catalog_manager
from atlanticus.web.manager import ManagerPrincipal


class FakeDash:
    def __init__(self):
        self.handlers = []

    def callback(self, *args, **kwargs):
        def decorate(handler):
            self.handlers.append(handler)
            return handler

        return decorate


class FakeManager:
    def __init__(self):
        self.calls = []

    def inspect(self):
        self.calls.append('inspect')
        return ToolCatalogReview(
            fingerprint='a' * 64,
            current_revision=None,
            can_confirm=True,
            issue=None,
            connections=(
                ToolConnectionSummary(
                    connection_name='mina',
                    status='READY',
                    issue=None,
                    tools=(
                        ToolCandidateSummary(
                            connection_name='mina',
                            tool_key='mine',
                            display_name='Mina',
                            kind='integrated_operations',
                            source_release_id='release-1',
                        ),
                    ),
                ),
            ),
        )

    def confirm(self, **kwargs):
        self.calls.append(('confirm', kwargs))
        return self.adopted()

    def adopted(self):
        self.calls.append('adopted')
        return AdoptedToolCatalog(revision='b' * 64, tools=())


def _register(monkeypatch, access=()):
    manager = FakeManager()
    principal = ManagerPrincipal('user', 'User', access_keys=access)
    entry = catalog_manager.create_tool_catalog_manager_entry(
        manager=manager,
        principal_provider=lambda: principal,
        group_key='configuration',
    )
    app = FakeDash()
    entry.web_module.register_callbacks(app, object())
    trigger = SimpleNamespace(triggered_id=None)
    monkeypatch.setattr(catalog_manager, 'ctx', trigger)
    return app.handlers, manager, trigger


def test_unauthorized_callbacks_never_read_cosmos_or_blob(monkeypatch) -> None:
    handlers, manager, trigger = _register(monkeypatch)
    trigger.triggered_id = 'acc-tool-catalog-discover'
    state, message, _ = handlers[0](1, 0, 0, None)
    assert state is None
    assert message == 'Operación no autorizada.'
    assert manager.calls == []


def test_discover_and_confirm_are_distinct_authorized_actions(monkeypatch) -> None:
    handlers, manager, trigger = _register(monkeypatch, ('tools.manage',))
    trigger.triggered_id = 'acc-tool-catalog-discover'
    state, _, _ = handlers[0](1, 0, 0, None)
    assert manager.calls == ['inspect']
    assert state['connections'][0]['tools'][0]['key'] == 'mine'
    assert set(state) == {'fingerprint', 'revision', 'can_confirm', 'connections', 'issue'}
    _, disabled = handlers[1](state)
    assert disabled is False
    trigger.triggered_id = 'acc-tool-catalog-confirm'
    cleared, message, _ = handlers[0](1, 1, 0, state)
    assert cleared is None
    assert message == 'Consolidación confirmada.'
    assert manager.calls[1][1] == {
        'expected_fingerprint': 'a' * 64,
        'expected_current_revision': None,
    }


def test_confirmation_conflict_requires_fresh_inspection(monkeypatch) -> None:
    handlers, manager, trigger = _register(monkeypatch, ('tools.manage',))

    def fail(**kwargs):
        raise ToolCatalogManagerConflictError('private')

    manager.confirm = fail
    trigger.triggered_id = 'acc-tool-catalog-confirm'
    state = {'fingerprint': 'a' * 64, 'revision': None, 'can_confirm': True}
    cleared, message, _ = handlers[0](0, 1, 0, state)
    assert cleared is None
    assert 'descubrimiento' in message
    assert 'private' not in message


def test_confirmation_without_valid_review_does_not_use_service(monkeypatch) -> None:
    handlers, manager, trigger = _register(monkeypatch, ('tools.manage',))
    trigger.triggered_id = 'acc-tool-catalog-confirm'
    cleared, _, _ = handlers[0](0, 1, 0, {'can_confirm': False})
    assert cleared is None
    assert manager.calls == []


def test_adopted_reads_without_discovering(monkeypatch) -> None:
    handlers, manager, trigger = _register(monkeypatch, ('tools.manage',))
    trigger.triggered_id = 'acc-tool-catalog-adopted'
    state, message, result = handlers[0](0, 0, 1, None)
    assert manager.calls == ['adopted']
    assert state is catalog_manager.no_update
    assert 'Storage' in message
    assert result is not catalog_manager.no_update


def test_preview_requires_confirmable_review(monkeypatch) -> None:
    handlers, _, _ = _register(monkeypatch, ('tools.manage',))
    assert handlers[1](None) == (None, True)
    _, disabled = handlers[1]({'connections': [], 'can_confirm': False})
    assert disabled is True
