from __future__ import annotations

# Identificadores propios de Navigation; no dependen del Header.


class AdaNavigationIds:
    DESKTOP_TOGGLE = 'ada-navigation-desktop-toggle'
    MOBILE_TOGGLE = 'ada-navigation-mobile-toggle'
    OFFCANVAS = 'ada-navigation-offcanvas'
    LOCATION = 'ada-navigation-location'
    MENU_CONTENT = 'ada-navigation-menu-content'
    GROUP_TOGGLE = 'ada-navigation-group-toggle'
    GROUP_COLLAPSE = 'ada-navigation-group-collapse'
    LINK = 'ada-navigation-link'

    @staticmethod
    def group_toggle(group_key: str) -> dict[str, str]:
        return {'type': AdaNavigationIds.GROUP_TOGGLE, 'group_key': group_key}

    @staticmethod
    def group_collapse(group_key: str) -> dict[str, str]:
        return {'type': AdaNavigationIds.GROUP_COLLAPSE, 'group_key': group_key}

    @staticmethod
    def link(link_key: str) -> dict[str, str]:
        return {'type': AdaNavigationIds.LINK, 'link_key': link_key}
