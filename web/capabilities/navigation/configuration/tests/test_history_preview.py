from atlanticus.web.navigation.configuration.web import build_navigation_history_preview


def _text(value: object) -> str:
    if value is None:
        return ''
    if isinstance(value, (str, int, float)):
        return str(value)
    children = getattr(value, 'children', None)
    if isinstance(children, (list, tuple)):
        return ' '.join(_text(item) for item in children)
    return _text(children)


def test_navigation_history_preview_shows_routes_sections_and_permissions() -> None:
    preview = build_navigation_history_preview(
        {
            'links': [
                {
                    'key': 'home',
                    'label': 'Inicio',
                    'href': '/',
                    'order': 0,
                    'enabled': True,
                    'new_tab': False,
                    'force_reload': False,
                    'allowed_profiles': [],
                }
            ],
            'groups': [
                {
                    'key': 'operations',
                    'label': 'Operaciones',
                    'order': 10,
                    'enabled': True,
                    'links': [
                        {
                            'key': 'alarms',
                            'label': 'Alarmas',
                            'href': '/alarms',
                            'order': 20,
                            'enabled': True,
                            'new_tab': True,
                            'force_reload': False,
                            'allowed_profiles': ['guest'],
                        }
                    ],
                }
            ],
        }
    )

    text = _text(preview)

    assert 'Enlaces raíz 1' in text
    assert 'Secciones 1' in text
    assert 'Inicio home /' in text
    assert 'Operaciones operations' in text
    assert 'Alarmas alarms /alarms' in text
    assert 'Perfiles: guest' in text
    assert 'Nueva pestaña' in text
