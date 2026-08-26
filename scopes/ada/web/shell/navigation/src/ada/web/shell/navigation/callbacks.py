from __future__ import annotations

from dash import ALL, MATCH, Dash, Input, Output, State

from ada.web.shell.navigation.ids import AdaNavigationIds
from atlanticus.web.services import ServiceRegistry


def register_ada_navigation_callbacks(app: Dash, _services: ServiceRegistry) -> None:
    app.clientside_callback(
        """
        function(nClicks, isOpen) {
            if (!nClicks) {
                return window.dash_clientside.no_update;
            }
            return !Boolean(isOpen);
        }
        """,
        Output(AdaNavigationIds.OFFCANVAS, 'is_open'),
        Input(AdaNavigationIds.TRIGGER, 'n_clicks'),
        State(AdaNavigationIds.OFFCANVAS, 'is_open'),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(nClicks, isOpen) {
            if (!nClicks) {
                return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            }
            const nextOpen = !Boolean(isOpen);
            const className = [
                'ada-navigation__button',
                'ada-navigation__group-button',
                nextOpen ? 'is-open' : '',
            ].filter(Boolean).join(' ');
            return [nextOpen, className];
        }
        """,
        Output(
            {'type': AdaNavigationIds.GROUP_COLLAPSE, 'group_key': MATCH},
            'is_open',
        ),
        Output(
            {'type': AdaNavigationIds.GROUP_TOGGLE, 'group_key': MATCH},
            'className',
        ),
        Input(
            {'type': AdaNavigationIds.GROUP_TOGGLE, 'group_key': MATCH},
            'n_clicks',
        ),
        State(
            {'type': AdaNavigationIds.GROUP_COLLAPSE, 'group_key': MATCH},
            'is_open',
        ),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(pathname, hrefs, classNames) {
            const normalize = (value) => {
                if (!value || value === '/') {
                    return '/';
                }
                return String(value).replace(/\\/+$/, '') || '/';
            };
            const current = normalize(pathname);
            return (hrefs || []).map((href, index) => {
                const source = String((classNames || [])[index] || '');
                const tokens = source.split(/\\s+/).filter(Boolean).filter((token) => token !== 'is-active');
                if (typeof href === 'string' && href.startsWith('/') && normalize(href) === current) {
                    tokens.push('is-active');
                }
                return Array.from(new Set(tokens)).join(' ');
            });
        }
        """,
        Output({'type': AdaNavigationIds.LINK, 'link_key': ALL}, 'className'),
        Input(AdaNavigationIds.LOCATION, 'pathname'),
        State({'type': AdaNavigationIds.LINK, 'link_key': ALL}, 'href'),
        State({'type': AdaNavigationIds.LINK, 'link_key': ALL}, 'className'),
    )
