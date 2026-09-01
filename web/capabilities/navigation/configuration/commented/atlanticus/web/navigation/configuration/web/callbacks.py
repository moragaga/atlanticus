# Hidrata Navigation únicamente desde un draft explícito y calcula la revisión del contenido realmente editable.
# Un workspace vacío no absorbe silenciosamente rutas publicadas al comenzar a editar.

from __future__ import annotations

import base64
from datetime import UTC, datetime

from dash import ALL, Input, Output, State, ctx, html, no_update

from atlanticus.web.navigation.configuration.bundle import (
    build_navigation_configuration_digest,
    decode_navigation_configuration_import,
)
from atlanticus.web.navigation.configuration.editor import (
    build_initial_catalog,
    create_group,
    link_parent_key,
    remove_group,
    remove_link,
    reorder_link,
    reorder_root_node,
    update_group,
    upsert_link,
)
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.navigation.configuration.profiles import selectable_profile_options
from atlanticus.web.navigation.configuration.web.ids import (
    ADD_GROUP_ID,
    ADD_ROOT_LINK_ID,
    CATALOG_STORE_ID,
    GROUP_CANCEL_ID,
    GROUP_EDITOR_STORE_ID,
    GROUP_ENABLED_ID,
    GROUP_ICON_ID,
    GROUP_KEY_ID,
    GROUP_MODAL_ID,
    GROUP_MODAL_TITLE_ID,
    GROUP_NAME_ID,
    GROUP_RESULT_ID,
    GROUP_SAVE_ID,
    IMPORT_RESULT_ID,
    IMPORT_UPLOAD_ID,
    LINK_CANCEL_ID,
    LINK_EDITOR_STORE_ID,
    LINK_ENABLED_ID,
    LINK_FORCE_RELOAD_ID,
    LINK_HREF_ID,
    LINK_ICON_ID,
    LINK_KEY_ID,
    LINK_MODAL_ID,
    LINK_MODAL_TITLE_ID,
    LINK_NAME_ID,
    LINK_NEW_TAB_ID,
    LINK_PROFILES_ID,
    LINK_RESULT_ID,
    LINK_SAVE_ID,
    LINK_SECTION_ID,
    MOUNT_STORE_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
    SOURCE_REVISION_STORE_ID,
    STRUCTURE_ID,
)
from atlanticus.web.navigation.configuration.web.models import NavigationAdminWebContext
from atlanticus.web.navigation.configuration.web.rendering import (
    navigation_section_options,
    navigation_structure,
)

_MODAL_CLOSED = 'atlanticus-navigation-admin__modal'
_MODAL_OPEN = 'atlanticus-navigation-admin__modal atlanticus-navigation-admin__modal--open'
_BROWSER_DRAFT_SCHEMA_VERSION = 1
_ROOT_SECTION_VALUE = '__root__'


def register_navigation_admin_callbacks(app: object, context: NavigationAdminWebContext) -> None:
    @app.callback(
        Output(CATALOG_STORE_ID, 'data'),
        Output(SOURCE_REVISION_STORE_ID, 'data'),
        Input(MOUNT_STORE_ID, 'data'),
        Input(context.draft_store_id, 'data'),
    )
    def load_browser_draft(_mounted: object, draft_data: dict[str, object] | None):
        if draft_data is None:
            return no_update, no_update
        try:
            catalog = _catalog_from_browser_draft(
                draft_data,
                context.draft_owner_provider(),
            )
            base_source_revision = _draft_base_source_revision(
                draft_data,
                owner_subject_id=context.draft_owner_provider(),
                fallback=None,
            )
        except Exception:
            return build_initial_catalog().to_document(), None
        return catalog.to_document(), base_source_revision

    @app.callback(
        Output(context.editor_revision_store_id, 'data'),
        Input(CATALOG_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def track_editor_revision(catalog_data: dict[str, object] | None):
        try:
            return build_navigation_configuration_digest(_catalog(catalog_data))
        except Exception:
            return None

    @app.callback(
        Output(STRUCTURE_ID, 'children'),
        Input(CATALOG_STORE_ID, 'data'),
    )
    def render_catalog(catalog_data: dict[str, object] | None):
        return navigation_structure(_catalog(catalog_data))

    @app.callback(
        Output(LINK_EDITOR_STORE_ID, 'data'),
        Output(LINK_MODAL_ID, 'className'),
        Output(LINK_MODAL_TITLE_ID, 'children'),
        Output(LINK_NAME_ID, 'value'),
        Output(LINK_KEY_ID, 'value'),
        Output(LINK_HREF_ID, 'value'),
        Output(LINK_ICON_ID, 'value'),
        Output(LINK_SECTION_ID, 'options'),
        Output(LINK_SECTION_ID, 'value'),
        Output(LINK_ENABLED_ID, 'value'),
        Output(LINK_NEW_TAB_ID, 'value'),
        Output(LINK_FORCE_RELOAD_ID, 'value'),
        Output(LINK_PROFILES_ID, 'options'),
        Output(LINK_PROFILES_ID, 'value'),
        Output(LINK_RESULT_ID, 'children'),
        Input(ADD_ROOT_LINK_ID, 'n_clicks'),
        Input({'type': 'atlanticus-navigation-group-add-link', 'key': ALL}, 'n_clicks'),
        Input({'type': 'atlanticus-navigation-link-edit', 'key': ALL}, 'n_clicks'),
        State(CATALOG_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def open_link_editor(
        root_clicks: int | None,
        _group_clicks: list[int | None],
        _edit_clicks: list[int | None],
        catalog_data: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        catalog = _catalog(catalog_data)
        if trigger == ADD_ROOT_LINK_ID and _click_is_real(root_clicks):
            return _link_editor_response(context=context, catalog=catalog)
        if (
            isinstance(trigger, dict)
            and trigger.get('type') == 'atlanticus-navigation-group-add-link'
            and _triggered_click_is_real()
        ):
            return _link_editor_response(
                context=context,
                catalog=catalog,
                parent_group_key=str(trigger['key']),
            )
        if (
            isinstance(trigger, dict)
            and trigger.get('type') == 'atlanticus-navigation-link-edit'
            and _triggered_click_is_real()
        ):
            key = str(trigger['key'])
            link = _find_link(catalog, key)
            if link is None:
                return (no_update,) * 15
            return _link_editor_response(
                context=context,
                catalog=catalog,
                editor_key=key,
                parent_group_key=link_parent_key(catalog, key),
                link=link,
            )
        return (no_update,) * 15

    @app.callback(
        Output(LINK_MODAL_ID, 'className', allow_duplicate=True),
        Input(LINK_CANCEL_ID, 'n_clicks'),
        prevent_initial_call=True,
    )
    def close_link_editor(clicks: int | None):
        return _MODAL_CLOSED if _click_is_real(clicks) else no_update

    @app.callback(
        Output(CATALOG_STORE_ID, 'data', allow_duplicate=True),
        Output(LINK_MODAL_ID, 'className', allow_duplicate=True),
        Output(LINK_RESULT_ID, 'children', allow_duplicate=True),
        Input(LINK_SAVE_ID, 'n_clicks'),
        State(LINK_EDITOR_STORE_ID, 'data'),
        State(LINK_NAME_ID, 'value'),
        State(LINK_HREF_ID, 'value'),
        State(LINK_ICON_ID, 'value'),
        State(LINK_SECTION_ID, 'value'),
        State(LINK_ENABLED_ID, 'value'),
        State(LINK_NEW_TAB_ID, 'value'),
        State(LINK_FORCE_RELOAD_ID, 'value'),
        State(LINK_PROFILES_ID, 'value'),
        State(CATALOG_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def save_link(
        clicks: int | None,
        editor: dict[str, object] | None,
        name: str | None,
        href: str | None,
        icon: str | None,
        section: str | None,
        enabled: list[str] | None,
        new_tab: list[str] | None,
        force_reload: list[str] | None,
        profiles: list[str] | None,
        catalog_data: dict[str, object] | None,
    ):
        if not _click_is_real(clicks):
            return no_update, no_update, no_update
        if not context.can_manage():
            return no_update, no_update, _error('Management access is denied')
        try:
            updated = upsert_link(
                _catalog(catalog_data),
                editor_key=_optional_text((editor or {}).get('key')),
                parent_group_key=_section_key(section),
                label=str(name or ''),
                href=str(href or ''),
                icon=_optional_text(icon),
                enabled='enabled' in (enabled or []),
                new_tab='new_tab' in (new_tab or []),
                force_reload='force_reload' in (force_reload or []),
                allowed_profiles=_profile_keys(profiles),
            )
        except Exception as error:
            return no_update, no_update, _error(str(error))
        return updated.to_document(), _MODAL_CLOSED, None

    @app.callback(
        Output(CATALOG_STORE_ID, 'data', allow_duplicate=True),
        Input({'type': 'atlanticus-navigation-link-delete', 'key': ALL}, 'n_clicks'),
        Input({'type': 'atlanticus-navigation-link-up', 'key': ALL}, 'n_clicks'),
        Input({'type': 'atlanticus-navigation-link-down', 'key': ALL}, 'n_clicks'),
        State(CATALOG_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def link_action(
        _delete_clicks: list[int | None],
        _up_clicks: list[int | None],
        _down_clicks: list[int | None],
        catalog_data: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        if (
            not isinstance(trigger, dict)
            or not _triggered_click_is_real()
            or not context.can_manage()
        ):
            return no_update
        catalog = _catalog(catalog_data)
        key = str(trigger['key'])
        try:
            match trigger.get('type'):
                case 'atlanticus-navigation-link-delete':
                    updated = remove_link(catalog, key=key)
                case 'atlanticus-navigation-link-up':
                    updated = reorder_link(catalog, key=key, direction=-1)
                case 'atlanticus-navigation-link-down':
                    updated = reorder_link(catalog, key=key, direction=1)
                case _:
                    return no_update
        except Exception:
            return no_update
        return updated.to_document()

    @app.callback(
        Output(GROUP_EDITOR_STORE_ID, 'data'),
        Output(GROUP_MODAL_ID, 'className'),
        Output(GROUP_MODAL_TITLE_ID, 'children'),
        Output(GROUP_NAME_ID, 'value'),
        Output(GROUP_KEY_ID, 'value'),
        Output(GROUP_ICON_ID, 'value'),
        Output(GROUP_ENABLED_ID, 'value'),
        Output(GROUP_RESULT_ID, 'children'),
        Input(ADD_GROUP_ID, 'n_clicks'),
        Input({'type': 'atlanticus-navigation-group-edit', 'key': ALL}, 'n_clicks'),
        State(CATALOG_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def open_group_editor(
        add_clicks: int | None,
        _edit_clicks: list[int | None],
        catalog_data: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        catalog = _catalog(catalog_data)
        if trigger == ADD_GROUP_ID and _click_is_real(add_clicks):
            return _group_editor_response()
        if (
            isinstance(trigger, dict)
            and trigger.get('type') == 'atlanticus-navigation-group-edit'
            and _triggered_click_is_real()
        ):
            group = next((item for item in catalog.groups if item.key == str(trigger['key'])), None)
            if group is None:
                return (no_update,) * 8
            return _group_editor_response(group=group)
        return (no_update,) * 8

    @app.callback(
        Output(GROUP_MODAL_ID, 'className', allow_duplicate=True),
        Input(GROUP_CANCEL_ID, 'n_clicks'),
        prevent_initial_call=True,
    )
    def close_group_editor(clicks: int | None):
        return _MODAL_CLOSED if _click_is_real(clicks) else no_update

    @app.callback(
        Output(CATALOG_STORE_ID, 'data', allow_duplicate=True),
        Output(GROUP_MODAL_ID, 'className', allow_duplicate=True),
        Output(GROUP_RESULT_ID, 'children', allow_duplicate=True),
        Input(GROUP_SAVE_ID, 'n_clicks'),
        State(GROUP_EDITOR_STORE_ID, 'data'),
        State(GROUP_NAME_ID, 'value'),
        State(GROUP_ICON_ID, 'value'),
        State(GROUP_ENABLED_ID, 'value'),
        State(CATALOG_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def save_group(
        clicks: int | None,
        editor: dict[str, object] | None,
        name: str | None,
        icon: str | None,
        enabled: list[str] | None,
        catalog_data: dict[str, object] | None,
    ):
        if not _click_is_real(clicks):
            return no_update, no_update, no_update
        if not context.can_manage():
            return no_update, no_update, _error('Management access is denied')
        try:
            catalog = _catalog(catalog_data)
            key = _optional_text((editor or {}).get('key'))
            if key is None:
                updated = create_group(
                    catalog,
                    label=str(name or ''),
                    icon=_optional_text(icon),
                    enabled='enabled' in (enabled or []),
                )
            else:
                updated = update_group(
                    catalog,
                    key=key,
                    label=str(name or ''),
                    icon=_optional_text(icon),
                    enabled='enabled' in (enabled or []),
                )
        except Exception as error:
            return no_update, no_update, _error(str(error))
        return updated.to_document(), _MODAL_CLOSED, None

    @app.callback(
        Output(CATALOG_STORE_ID, 'data', allow_duplicate=True),
        Input({'type': 'atlanticus-navigation-group-delete', 'key': ALL}, 'n_clicks'),
        Input({'type': 'atlanticus-navigation-group-up', 'key': ALL}, 'n_clicks'),
        Input({'type': 'atlanticus-navigation-group-down', 'key': ALL}, 'n_clicks'),
        State(CATALOG_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def group_action(
        _delete_clicks: list[int | None],
        _up_clicks: list[int | None],
        _down_clicks: list[int | None],
        catalog_data: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        if (
            not isinstance(trigger, dict)
            or not _triggered_click_is_real()
            or not context.can_manage()
        ):
            return no_update
        catalog = _catalog(catalog_data)
        key = str(trigger['key'])
        try:
            match trigger.get('type'):
                case 'atlanticus-navigation-group-delete':
                    updated = remove_group(catalog, key=key)
                case 'atlanticus-navigation-group-up':
                    updated = reorder_root_node(catalog, key=key, direction=-1)
                case 'atlanticus-navigation-group-down':
                    updated = reorder_root_node(catalog, key=key, direction=1)
                case _:
                    return no_update
        except Exception:
            return no_update
        return updated.to_document()

    @app.callback(
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        Output(CATALOG_STORE_ID, 'data', allow_duplicate=True),
        Output(IMPORT_RESULT_ID, 'children'),
        Input(IMPORT_UPLOAD_ID, 'contents'),
        State(SOURCE_REVISION_STORE_ID, 'data'),
        prevent_initial_call=True,
    )
    def import_configuration(
        contents: str | None,
        source_revision: str | None,
    ):
        if contents is None:
            return no_update, no_update, no_update
        if not context.can_manage():
            return no_update, no_update, _error('Management access is denied')
        try:
            if ',' not in contents:
                raise ValueError('Configuration file payload is invalid')
            payload = base64.b64decode(contents.split(',', 1)[1], validate=True)
            catalog = decode_navigation_configuration_import(payload).catalog
            draft = _browser_draft_document(
                catalog=catalog,
                owner_subject_id=context.draft_owner_provider(),
                base_source_revision=source_revision,
            )
        except Exception as error:
            return no_update, no_update, _error(str(error))
        return draft, catalog.to_document(), None

    @app.callback(
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        # Guardar actualiza a la vez el workspace activo y el checkpoint persistente recuperable.
        Output(context.saved_draft_store_id, 'data', allow_duplicate=True),
        Output(SAVE_RESULT_ID, 'children'),
        Input(SAVE_BUTTON_ID, 'n_clicks'),
        Input(context.draft_save_action_id, 'n_clicks'),
        State(CATALOG_STORE_ID, 'data'),
        State(SOURCE_REVISION_STORE_ID, 'data'),
        State(context.draft_store_id, 'data'),
        prevent_initial_call=True,
    )
    def save_navigation_draft(
        content_clicks: int | None,
        workflow_clicks: int | None,
        catalog_data: dict[str, object] | None,
        source_revision: str | None,
        current_draft: dict[str, object] | None,
    ):
        trigger = ctx.triggered_id
        if not _save_draft_click_is_real(
            trigger,
            content_clicks=content_clicks,
            workflow_clicks=workflow_clicks,
            workflow_id=context.draft_save_action_id,
        ):
            return no_update, no_update, no_update
        if not context.can_manage():
            return no_update, no_update, _error('Management access is denied')
        try:
            catalog = _catalog(catalog_data)
            draft = _browser_draft_document(
                catalog=catalog,
                owner_subject_id=context.draft_owner_provider(),
                base_source_revision=_draft_base_source_revision(
                    current_draft,
                    owner_subject_id=context.draft_owner_provider(),
                    fallback=source_revision,
                ),
            )
        except Exception as error:
            return no_update, no_update, _error(str(error))
        return draft, draft, None


def _link_editor_response(
    *,
    context: NavigationAdminWebContext,
    catalog: NavigationConfigurationCatalog,
    parent_group_key: str | None = None,
    editor_key: str | None = None,
    link=None,
):
    selected_profiles = list(link.allowed_profiles) if link is not None else []
    profile_options = _profile_options(context, extra_keys=tuple(selected_profiles))
    section_options = navigation_section_options(catalog)
    if link is None and any(option['value'] == 'guest' for option in profile_options):
        selected_profiles = ['guest']
    section_value = parent_group_key or _ROOT_SECTION_VALUE
    return (
        {'key': editor_key},
        _MODAL_OPEN,
        'Editar enlace' if editor_key else 'Nuevo enlace',
        link.label if link else '',
        link.key if link else '',
        link.href if link else '',
        link.icon if link else '',
        section_options,
        section_value,
        ['enabled'] if link is None or link.enabled else [],
        ['new_tab'] if link is not None and link.new_tab else [],
        ['force_reload'] if link is not None and link.force_reload else [],
        profile_options,
        selected_profiles,
        None,
    )


def _group_editor_response(*, group=None):
    return (
        {'key': group.key if group else None},
        _MODAL_OPEN,
        'Editar sección' if group else 'Nueva sección',
        group.label if group else '',
        group.key if group else '',
        group.icon if group else '',
        ['enabled'] if group is None or group.enabled else [],
        None,
    )


def _profile_options(
    context: NavigationAdminWebContext,
    *,
    extra_keys: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    provider = context.profile_options_provider
    try:
        external = provider() if provider is not None else ()
    except Exception:
        external = ()
    options = [
        {'label': profile.label, 'value': profile.key}
        for profile in selectable_profile_options(external)
    ]
    known = {option['value'] for option in options}
    options.extend({'label': key, 'value': key} for key in extra_keys if key not in known)
    return options


def _catalog(data: dict[str, object] | None) -> NavigationConfigurationCatalog:
    if not isinstance(data, dict):
        raise ValueError('Navigation catalog is not available')
    return NavigationConfigurationCatalog.from_document(data)


def _find_link(catalog: NavigationConfigurationCatalog, key: str):
    for link in catalog.links:
        if link.key == key:
            return link
    for group in catalog.groups:
        for link in group.links:
            if link.key == key:
                return link
    return None


def _profile_keys(selected: list[str] | None) -> tuple[str, ...]:
    result: list[str] = []
    for raw in selected or []:
        key = str(raw).strip().casefold()
        if not key or any(character.isspace() for character in key):
            raise ValueError('Navigation profile key is invalid')
        if key in {'local', 'administrator'}:
            continue
        if key not in result:
            result.append(key)
    return tuple(result)


def _section_key(value: str | None) -> str | None:
    normalized = _optional_text(value)
    if normalized in {None, _ROOT_SECTION_VALUE}:
        return None
    return normalized


def _catalog_from_browser_draft(
    data: dict[str, object] | None,
    owner_subject_id: str,
) -> NavigationConfigurationCatalog:
    if not isinstance(data, dict) or data.get('schema_version') != 1:
        raise ValueError('Browser draft does not exist')
    if str(data.get('owner_subject_id', '')).strip() != owner_subject_id.strip():
        raise ValueError('Browser draft belongs to another user')
    payload = data.get('payload')
    if not isinstance(payload, dict):
        raise ValueError('Browser draft payload is invalid')
    catalog = NavigationConfigurationCatalog.from_document(dict(payload))
    if str(data.get('revision', '')).strip() != build_navigation_configuration_digest(catalog):
        raise ValueError('Browser draft revision does not match content')
    return catalog


def _browser_draft_document(
    *,
    catalog: NavigationConfigurationCatalog,
    owner_subject_id: str,
    base_source_revision: str | None,
) -> dict[str, object]:
    owner = owner_subject_id.strip()
    if not owner:
        raise ValueError('Browser draft owner is required')
    return {
        'schema_version': _BROWSER_DRAFT_SCHEMA_VERSION,
        'owner_subject_id': owner,
        'revision': build_navigation_configuration_digest(catalog),
        'saved_at': datetime.now(UTC).isoformat(),
        'base_source_revision': base_source_revision,
        'payload': catalog.to_document(),
    }


def _draft_base_source_revision(
    data: dict[str, object] | None,
    *,
    owner_subject_id: str,
    fallback: str | None,
) -> str | None:
    if not isinstance(data, dict):
        return fallback
    if str(data.get('owner_subject_id', '')).strip() != owner_subject_id.strip():
        return fallback
    value = data.get('base_source_revision')
    return _optional_text(value)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _save_draft_click_is_real(
    trigger: object,
    *,
    content_clicks: int | None,
    workflow_clicks: int | None,
    workflow_id: object,
) -> bool:
    if trigger == SAVE_BUTTON_ID:
        return _click_is_real(content_clicks)
    if trigger == workflow_id:
        return _click_is_real(workflow_clicks)
    return False


def _triggered_click_is_real() -> bool:
    triggered = ctx.triggered
    if not triggered:
        return False
    return _click_is_real(triggered[0].get('value'))


def _click_is_real(value: int | None) -> bool:
    return isinstance(value, int) and value > 0


def _error(message: str) -> object:
    return html.Div(message, className='atlanticus-navigation-admin__error')
