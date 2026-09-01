from atlanticus.web.users.configuration.web import build_users_history_preview


def _text(value: object) -> str:
    if value is None:
        return ''
    if isinstance(value, (str, int, float)):
        return str(value)
    children = getattr(value, 'children', None)
    if isinstance(children, (list, tuple)):
        return ' '.join(_text(item) for item in children)
    return _text(children)


def test_users_history_preview_shows_profiles_and_assignments() -> None:
    preview = build_users_history_preview(
        {
            'administrator_background_color': '#26425A',
            'administrator_text_color': '#FFFFFF',
            'guest_background_color': '#D6DADE',
            'guest_text_color': '#0D1B2A',
            'profiles': [
                {
                    'key': 'operator',
                    'label': 'Operador',
                    'background_color': '#C9A24B',
                    'text_color': '#0D1B2A',
                }
            ],
            'users': [
                {
                    'user_id': 'user:example',
                    'display_name': 'Jane Doe',
                    'email': 'jane@example.com',
                    'profile_key': 'operator',
                    'enabled': True,
                    'issuer': None,
                    'subject_id': None,
                }
            ],
        }
    )

    text = _text(preview)

    assert 'Perfiles 4' in text
    assert 'Perfiles personalizados 1' in text
    assert 'Operador operator' in text
    assert 'Jane Doe user:example' in text
    assert 'jane@example.com' in text
    assert 'Perfil: operator' in text
    assert 'Activo' in text
