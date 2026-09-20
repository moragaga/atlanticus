# Los callbacks traducen el ProfileCatalog a opciones de UI sin introducir perfiles base.
# Las claves ya persistidas se conservan visualmente para evitar pérdida accidental al editar.
from __future__ import annotations

import base64

from dash import ALL, Input, Output, State, ctx, html, no_update

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
from atlanticus.web.navigation.configuration.exchange import (
    build_navigation_configuration_digest,
    decode_navigation_configuration_import,
)
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.navigation.configuration.profiles import profile_options
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
    STRUCTURE_EXPANDED_GROUPS_STORE_ID,
    STRUCTURE_ID,
    STRUCTURE_NEXT_ID,
    STRUCTURE_PAGE_SIZE_ID,
    STRUCTURE_PAGE_STORE_ID,
    STRUCTURE_PREVIOUS_ID,
    group_toggle_id,
    structure_page_id,
)
from atlanticus.web.navigation.configuration.web.models import NavigationAdminWebContext
from atlanticus.web.navigation.configuration.web.rendering import (
    navigation_section_options,
    navigation_structure_page,
    render_navigation_structure,
)
from atlanticus.web.pagination import ALLOWED_PAGE_SIZES, DEFAULT_PAGE_SIZE, PageRequest

_MODAL_CLOSED = 'atlanticus-navigation-admin__modal'
_MODAL_OPEN = 'atlanticus-navigation-admin__modal atlanticus-navigation-admin__modal--open'
_ROOT_SECTION_VALUE = '__root__'


def register_navigation_admin_callbacks(app: object, context: NavigationAdminWebContext) -> None:
    @app.callback(
        Output(CATALOG_STORE_ID, 'data'),
        Input(MOUNT_STORE_ID, 'data'),
        Input(context.draft_store_id, 'data'),
    )
    def load_browser_draft(_mounted: object, draft_data: dict[str, object] | None):
        try:
            payload = context.workspace_payload_reader(draft_data)
            if payload is None:
                return build_initial_catalog().to_document()
            return NavigationConfigurationCatalog.from_document(dict(payload)).to_document()
        except Exception:
            return build_initial_catalog().to_document()

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
        Output(STRUCTURE_PAGE_STORE_ID, 'data'),
        Output(STRUCTURE_EXPANDED_GROUPS_STORE_ID, 'data'),
        Input(CATALOG_STORE_ID, 'data'),
        Input(STRUCTURE_PREVIOUS_ID, 'n_clicks'),
        Input(STRUCTURE_NEXT_ID, 'n_clicks'),
        Input(structure_page_id(ALL), 'n_clicks'),
        Input(STRUCTURE_PAGE_SIZE_ID, 'value'),
        Input(group_toggle_id(ALL), 'n_clicks'),
        State(STRUCTURE_PAGE_STORE_ID, 'data'),
        State(STRUCTURE_EXPANDED_GROUPS_STORE_ID, 'data'),
    )
    def render_catalog(
        catalog_data: dict[str, object] | None,
        previous_clicks: int | None,
        next_clicks: int | None,
        _page_clicks: list[int | None],
        page_size: int | None,
        _toggle_clicks: list[int | None],
        current_page: int | None,
        expanded_group_keys: list[str] | None,
    ):
        # La página sólo controla la ventana de nodos raíz/sección.
        # El estado expandido es efímero y nunca entra al documento Source.
        catalog = _catalog(catalog_data)
        resolved_page_size = (
            page_size
            if isinstance(page_size, int)
            and not isinstance(page_size, bool)
            and page_size in ALLOWED_PAGE_SIZES
            else DEFAULT_PAGE_SIZE
        )
        page_number = (
            current_page
            if isinstance(current_page, int)
            and not isinstance(current_page, bool)
            and current_page > 0
            else 1
        )
        expanded = [str(key) for key in expanded_group_keys or []]
        trigger = ctx.triggered_id
        if trigger == STRUCTURE_PREVIOUS_ID and _click_is_real(previous_clicks):
            page_number = max(1, page_number - 1)
        elif trigger == STRUCTURE_NEXT_ID and _click_is_real(next_clicks):
            page_number += 1
        elif trigger == STRUCTURE_PAGE_SIZE_ID:
            page_number = 1
        elif (
            isinstance(trigger, dict)
            and trigger.get('type') == 'atlanticus-navigation-structure-page'
            and _triggered_click_is_real()
        ):
            page_number = max(1, int(trigger.get('index', 1)))
        elif (
            isinstance(trigger, dict)
            and trigger.get('type') == 'atlanticus-navigation-group-toggle'
            and _triggered_click_is_real()
        ):
            key = str(trigger.get('key', ''))
            if key in expanded:
                expanded.remove(key)
            elif key:
                expanded.append(key)
        valid_groups = {group.key for group in catalog.groups}
        expanded = [key for key in expanded if key in valid_groups]
        page = navigation_structure_page(
            catalog,
            PageRequest(page_number=page_number, page_size=resolved_page_size),
        )
        return (
            render_navigation_structure(page, expanded_group_keys=tuple(expanded)),
            page.request.page_number,
            expanded,
        )

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
        Input(LINK_CANCEL_ID + '-header', 'n_clicks'),
        prevent_initial_call=True,
    )
    def close_link_editor(clicks: int | None, header_clicks: int | None):
        if _click_is_real(clicks) or _click_is_real(header_clicks):
            return _MODAL_CLOSED
        return no_update

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
        enabled: bool | None,
        new_tab: bool | None,
        force_reload: bool | None,
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
                enabled=bool(enabled),
                new_tab=bool(new_tab),
                force_reload=bool(force_reload),
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
        Input(GROUP_CANCEL_ID + '-header', 'n_clicks'),
        prevent_initial_call=True,
    )
    def close_group_editor(clicks: int | None, header_clicks: int | None):
        if _click_is_real(clicks) or _click_is_real(header_clicks):
            return _MODAL_CLOSED
        return no_update

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
        enabled: bool | None,
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
                    enabled=bool(enabled),
                )
            else:
                updated = update_group(
                    catalog,
                    key=key,
                    label=str(name or ''),
                    icon=_optional_text(icon),
                    enabled=bool(enabled),
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
        State(context.draft_store_id, 'data'),
        prevent_initial_call=True,
    )
    def import_configuration(
        contents: str | None,
        current_draft: dict[str, object] | None,
    ):
        if contents is None:
            return no_update, no_update, no_update
        if not context.can_manage():
            return no_update, no_update, _error('Management access is denied')
        try:
            if ',' not in contents:
                raise ValueError('Configuration file payload is invalid')
            payload = base64.b64decode(contents.split(',', 1)[1], validate=True)
            catalog = decode_navigation_configuration_import(payload)
            draft = context.workspace_payload_writer(current_draft, catalog.to_document())
        except Exception as error:
            return no_update, no_update, _error(str(error))
        return draft, catalog.to_document(), None

    @app.callback(
        Output(context.draft_store_id, 'data', allow_duplicate=True),
        Output(context.saved_draft_store_id, 'data', allow_duplicate=True),
        Output(SAVE_RESULT_ID, 'children'),
        Input(SAVE_BUTTON_ID, 'n_clicks'),
        Input(context.draft_save_action_id, 'n_clicks'),
        State(CATALOG_STORE_ID, 'data'),
        State(context.draft_store_id, 'data'),
        prevent_initial_call=True,
    )
    def save_navigation_draft(
        content_clicks: int | None,
        workflow_clicks: int | None,
        catalog_data: dict[str, object] | None,
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
            draft = context.workspace_payload_writer(current_draft, catalog.to_document())
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
        bool(link is None or link.enabled),
        bool(link is not None and link.new_tab),
        bool(link is not None and link.force_reload),
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
        bool(group is None or group.enabled),
        None,
    )


def _profile_options(
    context: NavigationAdminWebContext,
    *,
    extra_keys: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    options = [
        {'label': profile.label, 'value': profile.key}
        for profile in profile_options(context.profile_options_provider)
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
        if key not in result:
            result.append(key)
    return tuple(result)


def _section_key(value: str | None) -> str | None:
    normalized = _optional_text(value)
    if normalized in {None, _ROOT_SECTION_VALUE}:
        return None
    return normalized


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
    if isinstance(trigger, dict) and isinstance(workflow_id, dict):
        return dict(trigger) == dict(workflow_id) and _click_is_real(workflow_clicks)
    return trigger == workflow_id and _click_is_real(workflow_clicks)


def _triggered_click_is_real() -> bool:
    triggered = ctx.triggered
    if not triggered:
        return False
    return _click_is_real(triggered[0].get('value'))


def _click_is_real(value: int | None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _error(message: str) -> object:
    return html.Div(message, className='atlanticus-navigation-admin__error')
