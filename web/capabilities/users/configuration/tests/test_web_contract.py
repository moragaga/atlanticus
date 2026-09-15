from inspect import signature
from types import SimpleNamespace

import pytest

pytest.importorskip('dash')
from dash import Input, State

from atlanticus.web.source.models import SourceKey, SourceSnapshot
from atlanticus.web.users.configuration import (
    UsersProfilesAdminDraft,
    UsersProfilesAdministrationService,
    UsersProfilesConfiguration,
    default_users_profiles_configuration,
)
from atlanticus.web.users.configuration.web import (
    UsersAdminWebContext,
    build_users_admin_configuration,
    canonical_callbacks as users_callbacks,
    create_users_admin_web_module,
)
from atlanticus.web.users.configuration.web.canonical_callbacks import (
    register_users_admin_callbacks,
)
from atlanticus.web.users.configuration.web.ids import (
    ADMINISTRATOR_BACKGROUND_COLOR_ID,
    ADMINISTRATOR_TEXT_COLOR_ID,
    CATALOG_STORE_ID,
    DISCOVERED_TAB_ID,
    DRAFT_BASIS_STORE_ID,
    PROFILE_BACKGROUND_COLOR_ID,
    PROFILE_TAB_ID,
    PROFILE_TEXT_COLOR_ID,
    PROJECTION_NAME_ID,
    SAVE_BUTTON_ID,
    SECTION_STORE_ID,
    SOURCE_NAME_ID,
    USER_SAVE_ID,
    USERS_TAB_ID,
    discovered_add_id,
)
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import PendingUserRecord


class _CallbackRecorder:
    def __init__(self) -> None:
        self.callbacks: dict[str, tuple[tuple[object, ...], dict[str, object], object]] = {}

    def callback(self, *dependencies: object, **options: object):
        def register(function):
            self.callbacks[function.__name__] = (dependencies, options, function)
            return function

        return register


class _Source:
    def __init__(self) -> None:
        self.source_key = SourceKey('users')
        self.snapshot = SourceSnapshot(
            source_key=self.source_key,
            current=None,
            concurrency_token=None,
        )
        self.publish_attempted = False

    def get_current(self) -> SourceSnapshot:
        return self.snapshot

    def load_release(self, _release_ref):
        raise AssertionError('A source without current release must not be loaded')

    def publish_configuration(self, *_args, **_kwargs):
        self.publish_attempted = True
        raise AssertionError('Saving a browser draft must not publish Source')


class _PendingReader:
    def __init__(self, users: tuple[PendingUserRecord, ...] = ()) -> None:
        self._users = users

    def list_pending(self) -> tuple[PendingUserRecord, ...]:
        return self._users


def _context(
    pending_users: tuple[PendingUserRecord, ...] = (),
) -> tuple[UsersAdminWebContext, _Source]:
    source = _Source()
    administration = UsersProfilesAdministrationService(
        source=source,
        pending=_PendingReader(pending_users),
    )
    return (
        UsersAdminWebContext(
            administration=administration,
            draft_store_id='draft',
            saved_draft_store_id='saved-draft',
            draft_save_action_id='workflow-save-draft',
            workflow_refresh_signal_id='workflow-refresh',
            editor_revision_store_id='editor-revision',
            draft_owner_provider=lambda: 'tester',
            source_name='Users Source',
            projection_name='Users Projection',
        ),
        source,
    )


def _walk(component: object):
    yield component
    children = getattr(component, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if child is not None:
                yield from _walk(child)
    elif children is not None and not isinstance(children, (str, int, float, bool)):
        yield from _walk(children)


def _component(layout: object, component_id: object) -> object:
    for item in _walk(layout):
        if getattr(item, 'id', None) == component_id:
            return item
    raise AssertionError(f'Component {component_id!r} was not found')


def _text(component: object) -> str:
    values: list[str] = []
    for item in _walk(component):
        children = getattr(item, 'children', None)
        if isinstance(children, str):
            values.append(children)
    return ' '.join(values)


def _registered_callbacks(context: UsersAdminWebContext) -> _CallbackRecorder:
    recorder = _CallbackRecorder()
    register_users_admin_callbacks(recorder, context)
    return recorder


def test_users_admin_layout_starts_with_canonical_local_workspace() -> None:
    context, _source = _context()

    layout = build_users_admin_configuration(context)
    configuration = UsersProfilesConfiguration.from_document(
        _component(layout, CATALOG_STORE_ID).data
    )

    assert configuration.users.users == ()
    assert tuple(profile.key for profile in configuration.profiles.profiles) == (
        'administrator',
    )
    assert _component(layout, DRAFT_BASIS_STORE_ID).data is None
    assert _component(layout, SECTION_STORE_ID).data == 'profiles'
    assert _text(_component(layout, SOURCE_NAME_ID)) == 'Users Source'
    assert _text(_component(layout, PROJECTION_NAME_ID)) == 'Users Projection'


def test_users_admin_exposes_profiles_users_and_pending_as_real_sections() -> None:
    context, _source = _context()
    layout = build_users_admin_configuration(context)

    assert _text(_component(layout, PROFILE_TAB_ID)) == 'Perfiles'
    assert _text(_component(layout, USERS_TAB_ID)) == 'Usuarios'
    assert _text(_component(layout, DISCOVERED_TAB_ID)) == 'Pendientes'


def test_users_admin_only_exposes_functional_profile_color_controls() -> None:
    context, _source = _context()
    layout = build_users_admin_configuration(context)

    for component_id in (
        ADMINISTRATOR_BACKGROUND_COLOR_ID,
        ADMINISTRATOR_TEXT_COLOR_ID,
        PROFILE_BACKGROUND_COLOR_ID,
        PROFILE_TEXT_COLOR_ID,
    ):
        control = _component(layout, component_id)
        assert getattr(control, 'type', None) == 'color'
        value = getattr(control, 'value', None)
        assert isinstance(value, str)
        assert value.startswith('#')


def test_users_admin_web_module_owns_its_asset_layer() -> None:
    context, _source = _context()

    module = create_users_admin_web_module(context)

    assert module.name == 'atlanticus-users-configuration'
    assert len(module.asset_layers) == 1
    assert module.asset_layers[0].name == 'atlanticus_users_configuration'
    assert module.asset_layers[0].package == 'atlanticus.web.users.configuration'


def test_users_admin_callback_registration_matches_function_arity() -> None:
    context, _source = _context()
    recorder = _registered_callbacks(context)

    assert recorder.callbacks

    for name, (dependencies, _options, function) in recorder.callbacks.items():
        inputs_and_states = sum(
            isinstance(dependency, (Input, State)) for dependency in dependencies
        )
        positional_parameters = len(
            [
                parameter
                for parameter in signature(function).parameters.values()
                if parameter.kind
                in {
                    parameter.POSITIONAL_ONLY,
                    parameter.POSITIONAL_OR_KEYWORD,
                }
            ]
        )
        assert positional_parameters == inputs_and_states, name


def test_users_admin_rehydrates_schema_2_draft_with_exact_source_snapshot() -> None:
    context, _source = _context()
    draft = context.administration.create_draft(owner_subject_id='tester')
    recorder = _registered_callbacks(context)
    load_browser_draft = recorder.callbacks['load_browser_draft'][2]

    result = load_browser_draft(1, draft.to_document())

    restored = UsersProfilesAdminDraft.from_document(result[3])
    assert result[0] == draft.configuration.to_document()
    assert restored == draft
    assert result[4] is None


def test_legacy_browser_draft_is_discarded_without_fabricating_provenance() -> None:
    context, _source = _context()
    recorder = _registered_callbacks(context)
    load_browser_draft = recorder.callbacks['load_browser_draft'][2]
    legacy = {
        'schema_version': 1,
        'owner_subject_id': 'tester',
        'revision': 'legacy',
        'saved_at': '2026-09-15T00:00:00+00:00',
        'base_source_revision': 'legacy-source',
        'payload': {},
    }

    result = load_browser_draft(1, legacy)

    recovered = UsersProfilesAdminDraft.from_document(result[3])
    assert recovered.owner_subject_id == 'tester'
    assert recovered.source_snapshot == context.administration.get_source_snapshot()
    assert result[4] is not None


def test_users_admin_save_draft_is_local_and_does_not_publish(monkeypatch) -> None:
    context, source = _context()
    basis = context.administration.create_draft(owner_subject_id='tester')
    recorder = _registered_callbacks(context)
    save_users_draft = recorder.callbacks['save_users_draft'][2]

    monkeypatch.setattr(
        users_callbacks,
        'ctx',
        SimpleNamespace(triggered_id=SAVE_BUTTON_ID),
    )

    draft_document, saved_document, basis_document, result = save_users_draft(
        1,
        None,
        basis.configuration.to_document(),
        basis.to_document(),
    )

    draft = UsersProfilesAdminDraft.from_document(draft_document)

    assert saved_document == draft_document
    assert basis_document == draft_document
    assert result is None
    assert draft.owner_subject_id == 'tester'
    assert draft.source_snapshot == basis.source_snapshot
    assert source.publish_attempted is False


def test_users_admin_can_materialize_pending_identity_into_canonical_draft(
    monkeypatch,
) -> None:
    pending = PendingUserRecord(
        user_id=build_user_key(issuer='entra', subject_id='subject-new'),
        issuer='entra',
        subject_id='subject-new',
        display_name='Pending User',
        email='pending@example.com',
    )
    context, _source = _context((pending,))
    recorder = _registered_callbacks(context)
    user_editor = recorder.callbacks['user_editor'][2]
    configuration = default_users_profiles_configuration()

    monkeypatch.setattr(
        users_callbacks,
        'ctx',
        SimpleNamespace(triggered_id=USER_SAVE_ID),
    )

    result = user_editor(
        None,
        None,
        None,
        None,
        None,
        1,
        [],
        [],
        {
            'mode': 'pending',
            'user_id': pending.user_id,
            'issuer': pending.issuer,
            'subject_id': pending.subject_id,
        },
        'Pending User',
        'pending@example.com',
        'administrator',
        True,
        configuration.to_document(),
    )

    updated = UsersProfilesConfiguration.from_document(result[-1])
    assert len(updated.users.users) == 1
    assert updated.users.users[0].user_id == pending.user_id
    assert updated.users.users[0].issuer == pending.issuer
    assert updated.users.users[0].subject_id == pending.subject_id
    assert updated.users.users[0].profile_key == 'administrator'


def test_pending_identity_that_disappeared_is_not_recreated_from_browser_state(
    monkeypatch,
) -> None:
    context, _source = _context()
    recorder = _registered_callbacks(context)
    user_editor = recorder.callbacks['user_editor'][2]
    missing_user_id = build_user_key(issuer='entra', subject_id='missing-subject')
    trigger = discovered_add_id(missing_user_id)

    monkeypatch.setattr(
        users_callbacks,
        'ctx',
        SimpleNamespace(triggered_id=trigger),
    )

    result = user_editor(
        None,
        [1],
        None,
        None,
        None,
        None,
        [],
        [trigger],
        None,
        None,
        None,
        None,
        None,
        default_users_profiles_configuration().to_document(),
    )

    assert result[1] is None
    assert result[10] is not None
