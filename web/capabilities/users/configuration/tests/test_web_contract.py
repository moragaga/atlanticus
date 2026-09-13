from inspect import signature
from types import SimpleNamespace

import pytest
from dash import Input, State

pytest.importorskip('dash')

from atlanticus.web.manager.projection import ManagerDraft
from atlanticus.web.users.configuration import (
    UsersConfigurationCatalog,
    compose_users_configuration_services,
)
from atlanticus.web.users.configuration.adapters import (
    MemoryPendingUsersReader,
    MemoryUsersConfigurationStore,
    MemoryUsersProjectionRepository,
)
from atlanticus.web.users.configuration.web import (
    UsersAdminWebContext,
    build_users_admin_configuration,
    callbacks as users_callbacks,
    create_users_admin_web_module,
)
from atlanticus.web.users.configuration.web.callbacks import (
    _browser_draft_document,
    register_users_admin_callbacks,
)
from atlanticus.web.users.configuration.web.ids import (
    ADMINISTRATOR_BACKGROUND_COLOR_ID,
    ADMINISTRATOR_TEXT_COLOR_ID,
    CATALOG_STORE_ID,
    DISCOVERED_TAB_ID,
    GUEST_BACKGROUND_COLOR_ID,
    GUEST_TEXT_COLOR_ID,
    PROFILE_BACKGROUND_COLOR_ID,
    PROFILE_TAB_ID,
    PROFILE_TEXT_COLOR_ID,
    PROJECTION_NAME_ID,
    SAVE_BUTTON_ID,
    SECTION_STORE_ID,
    SOURCE_NAME_ID,
    SOURCE_REVISION_STORE_ID,
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


def _context(
    pending_users: list[PendingUserRecord] | None = None,
) -> tuple[
    UsersAdminWebContext,
    MemoryUsersConfigurationStore,
    MemoryUsersProjectionRepository,
]:
    source = MemoryUsersConfigurationStore()
    projection = MemoryUsersProjectionRepository()
    pending = MemoryPendingUsersReader(users=list(pending_users or ()))
    services = compose_users_configuration_services(
        source=source,
        publisher=source,
        projection=projection,
        pending=pending,
        audit_actor_provider=lambda: 'tester',
    )
    return (
        UsersAdminWebContext(
            services=services,
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
        projection,
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


def test_users_admin_layout_starts_with_empty_local_workspace(monkeypatch) -> None:
    context, _source, _projection = _context()

    def fail_if_source_is_loaded():
        raise AssertionError('Users source must not be loaded while building the editor layout')

    monkeypatch.setattr(context.services.administration, 'load_source', fail_if_source_is_loaded)

    layout = build_users_admin_configuration(context)
    catalog = UsersConfigurationCatalog.from_document(_component(layout, CATALOG_STORE_ID).data)

    assert catalog.profiles == ()
    assert catalog.users == ()
    assert _component(layout, SOURCE_REVISION_STORE_ID).data is None
    assert _component(layout, SECTION_STORE_ID).data == 'profiles'
    assert _text(_component(layout, SOURCE_NAME_ID)) == 'Users Source'
    assert _text(_component(layout, PROJECTION_NAME_ID)) == 'Users Projection'


def test_users_admin_exposes_profiles_users_and_pending_as_real_sections() -> None:
    context, _source, _projection = _context()
    layout = build_users_admin_configuration(context)

    assert _text(_component(layout, PROFILE_TAB_ID)) == 'Perfiles'
    assert _text(_component(layout, USERS_TAB_ID)) == 'Usuarios'
    assert _text(_component(layout, DISCOVERED_TAB_ID)) == 'Pendientes'


def test_users_admin_color_controls_are_functional_color_inputs() -> None:
    context, _source, _projection = _context()
    layout = build_users_admin_configuration(context)

    color_ids = (
        ADMINISTRATOR_BACKGROUND_COLOR_ID,
        ADMINISTRATOR_TEXT_COLOR_ID,
        GUEST_BACKGROUND_COLOR_ID,
        GUEST_TEXT_COLOR_ID,
        PROFILE_BACKGROUND_COLOR_ID,
        PROFILE_TEXT_COLOR_ID,
    )

    for component_id in color_ids:
        control = _component(layout, component_id)
        assert getattr(control, 'type', None) == 'color'
        value = getattr(control, 'value', None)
        assert isinstance(value, str)
        assert value.startswith('#')


def test_users_admin_web_module_owns_its_asset_layer() -> None:
    context, _source, _projection = _context()

    module = create_users_admin_web_module(context)

    assert module.name == 'atlanticus-users-configuration'
    assert len(module.asset_layers) == 1
    assert module.asset_layers[0].name == 'atlanticus_users_configuration'
    assert module.asset_layers[0].package == 'atlanticus.web.users.configuration'


def test_users_admin_callback_registration_matches_function_arity() -> None:
    context, _source, _projection = _context()
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


def test_users_admin_rehydrates_catalog_and_source_revision_from_manager_draft() -> None:
    context, _source, _projection = _context()
    layout = build_users_admin_configuration(context)
    catalog_document = _component(layout, CATALOG_STORE_ID).data
    catalog = UsersConfigurationCatalog.from_document(catalog_document)
    draft = _browser_draft_document(
        catalog=catalog,
        owner_subject_id='tester',
        base_source_revision='source-11',
    )
    recorder = _registered_callbacks(context)
    load_browser_draft = recorder.callbacks['load_browser_draft'][2]

    result = load_browser_draft(1, draft)

    assert result[0] == catalog_document
    assert result[-1] == 'source-11'


def test_users_admin_save_draft_is_local_and_does_not_publish_or_project(monkeypatch) -> None:
    context, source, projection = _context()
    layout = build_users_admin_configuration(context)
    catalog_document = _component(layout, CATALOG_STORE_ID).data
    recorder = _registered_callbacks(context)
    save_users_draft = recorder.callbacks['save_users_draft'][2]

    monkeypatch.setattr(
        users_callbacks,
        'ctx',
        SimpleNamespace(triggered_id=SAVE_BUTTON_ID),
    )

    draft_document, saved_document, result = save_users_draft(
        1,
        None,
        catalog_document,
        'source-17',
        None,
    )

    draft = ManagerDraft.from_document(draft_document)

    assert saved_document == draft_document
    assert result is None
    assert draft.owner_subject_id == 'tester'
    assert draft.base_source_revision == 'source-17'
    assert draft.payload == catalog_document
    assert source.fetch_bundle() is None
    assert projection.load_state() is None

def test_users_admin_can_materialize_pending_identity_into_draft(monkeypatch) -> None:
    context, _source, _projection = _context()
    recorder = _registered_callbacks(context)
    user_editor = recorder.callbacks['user_editor'][2]
    catalog = UsersConfigurationCatalog()
    user_id = build_user_key(issuer='entra', subject_id='subject-new')

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
            'user_id': user_id,
            'issuer': 'entra',
            'subject_id': 'subject-new',
        },
        'Pending User',
        'pending@example.com',
        'administrator',
        True,
        catalog.to_document(),
    )

    updated = UsersConfigurationCatalog.from_document(result[-1])

    assert len(updated.users) == 1
    assert updated.users[0].user_id == user_id
    assert updated.users[0].issuer == 'entra'
    assert updated.users[0].subject_id == 'subject-new'
    assert updated.users[0].profile_key == 'administrator'

def test_pending_identity_metadata_can_be_completed_before_incorporation(monkeypatch) -> None:
    pending = PendingUserRecord(
        user_id=build_user_key(issuer='entra', subject_id='subject-pending'),
        issuer='entra',
        subject_id='subject-pending',
    )
    context, _source, _projection = _context([pending])
    recorder = _registered_callbacks(context)
    user_editor = recorder.callbacks['user_editor'][2]
    trigger = discovered_add_id(pending.user_id)

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
        UsersConfigurationCatalog().to_document(),
    )

    assert result[1]['mode'] == 'pending'
    assert result[1]['user_id'] == pending.user_id
    assert result[3] == ''
    assert result[4] == ''
    assert result[8] is False
    assert result[9] is False


def test_pending_identity_that_disappeared_is_not_recreated_from_browser_state(
    monkeypatch,
) -> None:
    context, _source, _projection = _context()
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
        UsersConfigurationCatalog().to_document(),
    )

    assert result[1] is None
    assert result[10] is not None
