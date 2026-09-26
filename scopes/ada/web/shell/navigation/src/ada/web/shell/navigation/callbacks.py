from __future__ import annotations

from dash import ALL, Dash, Input, Output, State

from ada.web.shell.navigation.ids import AdaNavigationIds
from atlanticus.web.services import ServiceRegistry


def register_ada_navigation_callbacks(app: Dash, _services: ServiceRegistry) -> None:
    app.clientside_callback(
        """
        function(mobileClicks, desktopClicks, pathname, isOpen, lastPath) {
            const context = window.dash_clientside.callback_context;
            const triggered = context && Array.isArray(context.triggered)
                ? context.triggered : [];
            const hasChanged = (key) => triggered.some((entry) =>
                entry && entry.prop_id === key);
            const noUpdate = window.dash_clientside.no_update;
            const path = typeof pathname === 'string' ? pathname : null;
            const rememberPath = path !== null && path !== lastPath ? path : noUpdate;

            const mobilePressed = hasChanged('ada-navigation-mobile-toggle.n_clicks') &&
                Number(mobileClicks) > 0;
            const desktopPressed = hasChanged('ada-navigation-desktop-toggle.n_clicks') &&
                Number(desktopClicks) > 0;
            if (mobilePressed || desktopPressed) {
                return [!Boolean(isOpen), rememberPath];
            }

            if (hasChanged('ada-navigation-location.pathname')) {
                const navigated = lastPath !== null && lastPath !== undefined &&
                    path !== null && path !== lastPath;
                return [navigated ? false : noUpdate, rememberPath];
            }
            return [noUpdate, rememberPath];
        }
        """,
        Output(AdaNavigationIds.OFFCANVAS, 'is_open'),
        Output(AdaNavigationIds.LAST_PATH, 'data'),
        Input(AdaNavigationIds.MOBILE_TOGGLE, 'n_clicks'),
        Input(AdaNavigationIds.DESKTOP_TOGGLE, 'n_clicks'),
        Input(AdaNavigationIds.LOCATION, 'pathname'),
        State(AdaNavigationIds.OFFCANVAS, 'is_open'),
        State(AdaNavigationIds.LAST_PATH, 'data'),
    )

    app.clientside_callback(
        """
        function(
            _groupClicks,
            pathname,
            openStates,
            collapseIds,
            toggleIds,
            toggleClassNames,
            routeGroups,
            hrefs,
            linkClassNames
        ) {
            const normalize = (value) => {
                if (!value || value === '/') {
                    return '/';
                }
                return String(value).replace(/\\/+$/, '') || '/';
            };

            const current = normalize(pathname);
            let activeGroupKey = null;
            for (const [href, groupKey] of Object.entries(routeGroups || {})) {
                if (normalize(href) === current) {
                    activeGroupKey = groupKey;
                    break;
                }
            }

            const openByKey = {};
            (collapseIds || []).forEach((id, index) => {
                if (id && id.group_key) {
                    openByKey[id.group_key] = Boolean((openStates || [])[index]);
                }
            });

            const context = window.dash_clientside.callback_context;
            const triggeredId = context ? context.triggered_id : null;
            if (
                triggeredId &&
                typeof triggeredId === 'object' &&
                triggeredId.type === 'ada-navigation-group-toggle'
            ) {
                const groupKey = triggeredId.group_key;
                if (groupKey && groupKey !== activeGroupKey) {
                    openByKey[groupKey] = !Boolean(openByKey[groupKey]);
                }
            }

            if (activeGroupKey) {
                openByKey[activeGroupKey] = true;
            }

            const nextOpenStates = (collapseIds || []).map(
                (id) => Boolean(id && openByKey[id.group_key])
            );

            const nextToggleClassNames = (toggleIds || []).map((id, index) => {
                const groupKey = id && id.group_key;
                const source = String((toggleClassNames || [])[index] || '');
                const tokens = source
                    .split(/\\s+/)
                    .filter(Boolean)
                    .filter(
                        (token) =>
                            token !== 'ada-navigation__group-button--open' &&
                            token !== 'ada-navigation__group-button--route-active'
                    );
                if (groupKey && openByKey[groupKey]) {
                    tokens.push('ada-navigation__group-button--open');
                }
                if (groupKey && groupKey === activeGroupKey) {
                    tokens.push('ada-navigation__group-button--route-active');
                }
                return Array.from(new Set(tokens)).join(' ');
            });

            const nextLinkClassNames = (hrefs || []).map((href, index) => {
                const source = String((linkClassNames || [])[index] || '');
                const tokens = source
                    .split(/\\s+/)
                    .filter(Boolean)
                    .filter((token) => token !== 'ada-navigation__link-wrapper--active');
                if (typeof href === 'string' && href.startsWith('/') && normalize(href) === current) {
                    tokens.push('ada-navigation__link-wrapper--active');
                }
                return Array.from(new Set(tokens)).join(' ');
            });

            return [nextOpenStates, nextToggleClassNames, nextLinkClassNames];
        }
        """,
        Output({'type': AdaNavigationIds.GROUP_COLLAPSE, 'group_key': ALL}, 'is_open'),
        Output({'type': AdaNavigationIds.GROUP_TOGGLE, 'group_key': ALL}, 'className'),
        Output({'type': AdaNavigationIds.LINK, 'link_key': ALL}, 'className'),
        Input({'type': AdaNavigationIds.GROUP_TOGGLE, 'group_key': ALL}, 'n_clicks'),
        Input(AdaNavigationIds.LOCATION, 'pathname'),
        State({'type': AdaNavigationIds.GROUP_COLLAPSE, 'group_key': ALL}, 'is_open'),
        State({'type': AdaNavigationIds.GROUP_COLLAPSE, 'group_key': ALL}, 'id'),
        State({'type': AdaNavigationIds.GROUP_TOGGLE, 'group_key': ALL}, 'id'),
        State({'type': AdaNavigationIds.GROUP_TOGGLE, 'group_key': ALL}, 'className'),
        State(AdaNavigationIds.ROUTE_GROUPS, 'data'),
        State({'type': AdaNavigationIds.LINK, 'link_key': ALL}, 'href'),
        State({'type': AdaNavigationIds.LINK, 'link_key': ALL}, 'className'),
    )
